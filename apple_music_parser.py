"""
Apple Music Data Parser

Parses Apple Music export data to extract listening history,
top songs, artists, genres, and listening statistics.
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Optional, Dict, List, Tuple, Set
import re


class AppleMusicParser:
    """Parser for Apple Music exported data."""
    
    def __init__(self, data_dir: str, 
                 exclude_artists: Optional[List[str]] = None,
                 exclude_songs: Optional[List[str]] = None,
                 exclude_genres: Optional[List[str]] = None):
        """
        Initialize parser with path to Apple Music Activity folder.
        
        Args:
            data_dir: Path to 'Apple Music Activity' folder from Apple data export
            exclude_artists: List of artist names to exclude (case-insensitive)
            exclude_songs: List of song names to exclude (case-insensitive)
            exclude_genres: List of genres to exclude (case-insensitive)
        """
        self.data_dir = Path(data_dir)
        self._play_activity = None
        self._daily_tracks = None
        self._track_history = None
        self._library_tracks = None
        self._library_artists = None
        self._top_content = None
        
        # Exclusion lists (lowercase for case-insensitive matching)
        self.exclude_artists = set(a.lower() for a in (exclude_artists or []))
        self.exclude_songs = set(s.lower() for s in (exclude_songs or []))
        self.exclude_genres = set(g.lower() for g in (exclude_genres or []))
    
    def _is_excluded_artist(self, artist: str) -> bool:
        """Check if an artist should be excluded."""
        if not artist:
            return False
        return artist.lower() in self.exclude_artists
    
    def _is_excluded_song(self, song: str) -> bool:
        """Check if a song should be excluded."""
        if not song:
            return False
        return song.lower() in self.exclude_songs
    
    def _is_excluded_genre(self, genre: str) -> bool:
        """Check if a genre should be excluded."""
        if not genre:
            return False
        return genre.lower() in self.exclude_genres
        
    def _load_csv(self, filename: str) -> Optional[pd.DataFrame]:
        """Load a CSV file from the data directory."""
        filepath = self.data_dir / filename
        if filepath.exists():
            try:
                return pd.read_csv(filepath, low_memory=False)
            except Exception as e:
                print(f"Warning: Could not load {filename}: {e}")
        return None
    
    def _load_json(self, filename: str) -> Optional[List[Dict]]:
        """Load a JSON file from the data directory."""
        filepath = self.data_dir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load {filename}: {e}")
        return None
    
    @property
    def play_activity(self) -> Optional[pd.DataFrame]:
        """Lazy load and return play activity data."""
        if self._play_activity is None:
            self._play_activity = self._load_csv("Apple Music Play Activity.csv")
        return self._play_activity
    
    def _build_track_identifier_map(self) -> Dict[int, Dict]:
        """
        Build a mapping from Track Identifier to full track metadata.
        
        Returns:
            Dictionary mapping track identifier (int) to metadata dict
        """
        if not hasattr(self, '_track_id_map'):
            self._track_id_map = {}
            
            if self.library_tracks:
                for track in self.library_tracks:
                    track_id = track.get('Track Identifier')
                    if track_id:
                        self._track_id_map[int(track_id)] = {
                            'Title': track.get('Title', ''),
                            'Artist': track.get('Artist', ''),
                            'Album': track.get('Album', ''),
                            'Genre': track.get('Genre', ''),
                            'Album Artist': track.get('Album Artist', ''),
                        }
        
        return self._track_id_map
    
    def _parse_track_description(self, description: str) -> Tuple[str, str]:
        """
        Parse "Artist - Song" format from Track Description.
        
        Args:
            description: Track Description string like "Regurgitator - I Will Lick Your Arsehole"
        
        Returns:
            Tuple of (artist, song_name)
        """
        if not description or pd.isna(description):
            return '', ''
        
        description = str(description).strip()
        if ' - ' in description:
            parts = description.split(' - ', 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
        
        return '', description
    
    @property
    def daily_tracks(self) -> Optional[pd.DataFrame]:
        """Lazy load and return daily tracks data, enriched with metadata."""
        if self._daily_tracks is None:
            df = self._load_csv("Apple Music - Play History Daily Tracks.csv")
            if df is not None and not df.empty:
                # Enrich with metadata from Library Tracks
                track_id_map = self._build_track_identifier_map()
                
                # Add columns if they don't exist
                if 'Song Name' not in df.columns:
                    df['Song Name'] = ''
                if 'Artist Name' not in df.columns:
                    df['Artist Name'] = ''
                if 'Album Name' not in df.columns:
                    df['Album Name'] = ''
                if 'Genre' not in df.columns:
                    df['Genre'] = ''
                
                # Enrich using Track Identifier
                if 'Track Identifier' in df.columns:
                    for idx, row in df.iterrows():
                        track_id = row.get('Track Identifier')
                        if pd.notna(track_id) and int(track_id) in track_id_map:
                            metadata = track_id_map[int(track_id)]
                            if not df.at[idx, 'Song Name']:
                                df.at[idx, 'Song Name'] = metadata.get('Title', '')
                            if not df.at[idx, 'Artist Name']:
                                df.at[idx, 'Artist Name'] = metadata.get('Artist', '') or metadata.get('Album Artist', '')
                            if not df.at[idx, 'Album Name']:
                                df.at[idx, 'Album Name'] = metadata.get('Album', '')
                            if not df.at[idx, 'Genre']:
                                df.at[idx, 'Genre'] = metadata.get('Genre', '')
                
                # Fallback: Parse Track Description if metadata still missing
                if 'Track Description' in df.columns:
                    for idx, row in df.iterrows():
                        # Only parse if we don't have the data yet
                        if not df.at[idx, 'Song Name'] or not df.at[idx, 'Artist Name']:
                            description = row.get('Track Description', '')
                            if pd.notna(description) and description:
                                artist, song = self._parse_track_description(description)
                                if artist and not df.at[idx, 'Artist Name']:
                                    df.at[idx, 'Artist Name'] = artist
                                if song and not df.at[idx, 'Song Name']:
                                    df.at[idx, 'Song Name'] = song
                
                self._daily_tracks = df
            else:
                self._daily_tracks = df
        return self._daily_tracks
    
    @property
    def track_history(self) -> Optional[pd.DataFrame]:
        """Lazy load and return track play history, enriched with metadata."""
        if self._track_history is None:
            df = self._load_csv("Apple Music - Track Play History.csv")
            if df is not None and not df.empty:
                # Add columns if they don't exist
                if 'Song Name' not in df.columns:
                    df['Song Name'] = ''
                if 'Artist Name' not in df.columns:
                    df['Artist Name'] = ''
                
                # Parse Track Name (format: "Artist - Song" or "Artist, Feature - Song")
                if 'Track Name' in df.columns:
                    for idx, row in df.iterrows():
                        track_name = row.get('Track Name', '')
                        if pd.notna(track_name) and track_name:
                            artist, song = self._parse_track_description(track_name)
                            if artist:
                                df.at[idx, 'Artist Name'] = artist
                            if song:
                                df.at[idx, 'Song Name'] = song
                
                self._track_history = df
            else:
                self._track_history = df
        return self._track_history
    
    @property
    def library_tracks(self) -> Optional[List[Dict]]:
        """Lazy load and return library tracks."""
        if self._library_tracks is None:
            self._library_tracks = self._load_json("Apple Music Library Tracks.json")
        return self._library_tracks
    
    @property
    def library_artists(self) -> Optional[List[Dict]]:
        """Lazy load and return library artists."""
        if self._library_artists is None:
            self._library_artists = self._load_json("Apple Music Library Artists.json")
        return self._library_artists
    
    @property
    def top_content(self) -> Optional[pd.DataFrame]:
        """Lazy load and return top content data."""
        if self._top_content is None:
            self._top_content = self._load_csv("Apple Music - Top Content.csv")
        return self._top_content
    
    def _parse_track_artist(self, track_name: str) -> Tuple[str, str]:
        """
        Parse 'Artist - Track Name' format.
        
        Returns:
            Tuple of (artist, track_name)
        """
        if ' - ' in track_name:
            parts = track_name.split(' - ', 1)
            return parts[0].strip(), parts[1].strip()
        return "Unknown Artist", track_name
    
    def get_play_stats(self, year: Optional[int] = None) -> Dict:
        """
        Get overall play statistics.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            Dictionary with play statistics
        """
        stats = {
            'total_plays': 0,
            'total_listening_time_ms': 0,
            'total_listening_time_hours': 0,
            'unique_songs': 0,
            'unique_artists': 0,
            'date_range': {'start': None, 'end': None}
        }
        
        if self.play_activity is not None:
            df = self.play_activity.copy()
            
            # Filter by year if specified
            if year and 'Event Start Timestamp' in df.columns:
                df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
                df = df[df['Event Start Timestamp'].dt.year == year]
            
            # Count plays (PLAY_END events are completed plays)
            if 'Event Type' in df.columns:
                plays = df[df['Event Type'] == 'PLAY_END']
                stats['total_plays'] = len(plays)
            else:
                stats['total_plays'] = len(df)
            
            # Total listening time
            if 'Play Duration Milliseconds' in df.columns:
                total_ms = df['Play Duration Milliseconds'].fillna(0).sum()
                stats['total_listening_time_ms'] = int(total_ms)
                stats['total_listening_time_hours'] = round(total_ms / (1000 * 60 * 60), 1)
            
            # Unique songs and artists
            if 'Song Name' in df.columns:
                stats['unique_songs'] = df['Song Name'].nunique()
            
            # Get date range
            if 'Event Start Timestamp' in df.columns:
                dates = pd.to_datetime(df['Event Start Timestamp'], errors='coerce').dropna()
                if len(dates) > 0:
                    stats['date_range']['start'] = dates.min().strftime('%Y-%m-%d')
                    stats['date_range']['end'] = dates.max().strftime('%Y-%m-%d')
        
        return stats
    
    def get_top_songs(self, limit: int = 10, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get top songs by play count and duration.
        
        Args:
            limit: Number of top songs to return
            year: Optional year to filter by
            
        Returns:
            DataFrame with top songs
        """
        if self.play_activity is None:
            return pd.DataFrame()
        
        df = self.play_activity.copy()
        
        # Filter by year if specified
        if year and 'Event Start Timestamp' in df.columns:
            df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
            df = df[df['Event Start Timestamp'].dt.year == year]
        
        # Filter for actual plays (not just starts)
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'PLAY_END']
        
        # Get song names
        if 'Song Name' not in df.columns:
            return pd.DataFrame()
        
        # Clean song names
        df = df[df['Song Name'].notna() & (df['Song Name'] != '')]
        
        # Apply exclusions
        if self.exclude_songs:
            df = df[~df['Song Name'].str.lower().isin(self.exclude_songs)]
        
        # Exclude songs by excluded artists (check Container Artist Name or parse from song)
        if self.exclude_artists and 'Container Artist Name' in df.columns:
            df = df[~df['Container Artist Name'].fillna('').str.lower().isin(self.exclude_artists)]
        
        # Aggregate by song
        song_stats = df.groupby('Song Name').agg({
            'Song Name': 'count',
            'Play Duration Milliseconds': 'sum'
        }).rename(columns={
            'Song Name': 'play_count',
            'Play Duration Milliseconds': 'total_duration_ms'
        })
        
        # Get album name if available
        if 'Album Name' in df.columns:
            albums = df.groupby('Song Name')['Album Name'].first()
            song_stats = song_stats.join(albums)
        
        # Get artist name if available (Container Artist Name)
        if 'Container Artist Name' in df.columns:
            artists = df.groupby('Song Name')['Container Artist Name'].first()
            song_stats = song_stats.join(artists.rename('Artist Name'))
        
        # Sort by play count, then by duration
        song_stats = song_stats.sort_values(
            ['play_count', 'total_duration_ms'], 
            ascending=[False, False]
        ).head(limit)
        
        song_stats = song_stats.reset_index()
        song_stats['total_duration_hours'] = (song_stats['total_duration_ms'] / (1000 * 60 * 60)).round(2)
        
        return song_stats
    
    def get_top_artists(self, limit: int = 10, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get top artists by play count.
        
        Uses multiple data sources to determine artist names.
        
        Args:
            limit: Number of top artists to return
            year: Optional year to filter by
            
        Returns:
            DataFrame with top artists
        """
        artists_counter = Counter()
        artist_duration = Counter()
        
        # Method 1: From play activity (Container Artist Name or Song Name parsing)
        if self.play_activity is not None:
            df = self.play_activity.copy()
            
            # Filter by year if specified
            if year and 'Event Start Timestamp' in df.columns:
                df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
                df = df[df['Event Start Timestamp'].dt.year == year]
            
            # Filter for actual plays
            if 'Event Type' in df.columns:
                df = df[df['Event Type'] == 'PLAY_END']
            
            # Try to get artist from Container Artist Name first
            if 'Container Artist Name' in df.columns:
                for _, row in df.iterrows():
                    artist = row.get('Container Artist Name', '')
                    if pd.notna(artist) and artist != '':
                        # Skip excluded artists
                        if self._is_excluded_artist(artist):
                            continue
                        artists_counter[artist] += 1
                        duration = row.get('Play Duration Milliseconds', 0)
                        if pd.notna(duration):
                            artist_duration[artist] += duration
        
        # Method 2: From daily tracks (parsed from track description)
        if self.daily_tracks is not None:
            df = self.daily_tracks.copy()
            
            # Filter by year if specified
            if year and 'Date Played' in df.columns:
                df['Date Played'] = pd.to_datetime(df['Date Played'].astype(str), format='%Y%m%d', errors='coerce')
                df = df[df['Date Played'].dt.year == year]
            
            if 'Track Description' in df.columns:
                for _, row in df.iterrows():
                    track_desc = row.get('Track Description', '')
                    if pd.notna(track_desc) and ' - ' in str(track_desc):
                        artist, _ = self._parse_track_artist(str(track_desc))
                        if artist != "Unknown Artist":
                            # Skip excluded artists
                            if self._is_excluded_artist(artist):
                                continue
                            play_count = row.get('Play Count', 1)
                            if pd.isna(play_count):
                                play_count = 1
                            artists_counter[artist] += int(play_count)
                            duration = row.get('Play Duration Milliseconds', 0)
                            if pd.notna(duration):
                                artist_duration[artist] += duration * int(play_count)
        
        # Method 3: From track history
        if self.track_history is not None:
            df = self.track_history.copy()
            
            if 'Track Name' in df.columns:
                for _, row in df.iterrows():
                    track_name = row.get('Track Name', '')
                    if pd.notna(track_name) and ' - ' in str(track_name):
                        artist, _ = self._parse_track_artist(str(track_name))
                        if artist != "Unknown Artist":
                            # Skip excluded artists
                            if self._is_excluded_artist(artist):
                                continue
                            artists_counter[artist] += 1
        
        # Create DataFrame from counter
        if not artists_counter:
            return pd.DataFrame(columns=['artist', 'play_count', 'total_duration_ms'])
        
        top_artists = pd.DataFrame([
            {
                'artist': artist,
                'play_count': count,
                'total_duration_ms': artist_duration.get(artist, 0)
            }
            for artist, count in artists_counter.most_common(limit)
        ])
        
        top_artists['total_duration_hours'] = (top_artists['total_duration_ms'] / (1000 * 60 * 60)).round(2)
        
        return top_artists
    
    def get_top_genres(self, limit: int = 5, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get top genres from library tracks and top content.
        
        Args:
            limit: Number of top genres to return
            year: Optional year to filter by
            
        Returns:
            DataFrame with top genres
        """
        genres_counter = Counter()
        
        # Known genre keywords to help identify actual genres
        KNOWN_GENRES = {
            'rock', 'pop', 'alternative', 'metal', 'hip-hop', 'hip hop', 'rap',
            'electronic', 'dance', 'r&b', 'country', 'jazz', 'classical', 'blues',
            'folk', 'indie', 'punk', 'soul', 'reggae', 'latin', 'world', 'new wave',
            'grunge', 'hard rock', 'heavy metal', 'progressive', 'psychedelic',
            'experimental', 'ambient', 'techno', 'house', 'edm', 'dubstep',
            'singer-songwriter', 'acoustic', 'adult alternative', 'alt-rock',
            'alternative rock', 'industrial', 'gothic', 'emo', 'hardcore',
            'post-punk', 'new age', 'soundtrack', 'comedy', 'spoken word'
        }
        
        # From library tracks - this is the most reliable source for genres
        if self.library_tracks:
            for track in self.library_tracks:
                genre = track.get('Genre', '')
                if genre:
                    # Skip excluded genres
                    if self._is_excluded_genre(genre):
                        continue
                    # Skip tracks from excluded artists
                    artist = track.get('Artist', '')
                    if self._is_excluded_artist(artist):
                        continue
                    play_count = track.get('Track Play Count', 1) or 1
                    genres_counter[genre] += play_count
        
        # From top content - only if it looks like a genre, not an artist
        if self.top_content is not None and not genres_counter:
            for _, row in self.top_content.iterrows():
                content = row.get('Content', '')
                duration = row.get('Play Duration Milliseconds', 0)
                if pd.notna(content) and pd.notna(duration):
                    content_str = str(content).strip()
                    content_lower = content_str.lower()
                    
                    # Only accept if it matches known genre patterns
                    # or is a short generic term without capital letters indicating a name
                    is_genre = any(g in content_lower for g in KNOWN_GENRES)
                    
                    if is_genre and duration > 0:
                        genres_counter[content_str] += int(duration)
        
        if not genres_counter:
            return pd.DataFrame(columns=['genre', 'play_count'])
        
        # Get top genres
        top_genres = pd.DataFrame([
            {'genre': genre, 'play_count': count}
            for genre, count in genres_counter.most_common(limit)
        ])
        
        return top_genres
    
    def get_listening_by_month(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get listening activity grouped by month.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            DataFrame with monthly listening stats
        """
        if self.play_activity is None:
            return pd.DataFrame()
        
        df = self.play_activity.copy()
        
        if 'Event Start Timestamp' not in df.columns:
            return pd.DataFrame()
        
        df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df.dropna(subset=['Event Start Timestamp'])
        
        if year:
            df = df[df['Event Start Timestamp'].dt.year == year]
        
        # Filter for actual plays
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'PLAY_END']
        
        df['month'] = df['Event Start Timestamp'].dt.to_period('M')
        
        monthly = df.groupby('month').agg({
            'Song Name': 'count',
            'Play Duration Milliseconds': 'sum'
        }).rename(columns={
            'Song Name': 'play_count',
            'Play Duration Milliseconds': 'total_duration_ms'
        })
        
        monthly['total_duration_hours'] = (monthly['total_duration_ms'] / (1000 * 60 * 60)).round(1)
        monthly = monthly.reset_index()
        monthly['month'] = monthly['month'].astype(str)
        
        return monthly
    
    def get_listening_by_hour(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get listening activity grouped by hour of day.
        Inspired by jcblsn/apple-music-wrapped.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            DataFrame with hourly listening stats
        """
        if self.play_activity is None:
            return pd.DataFrame()
        
        df = self.play_activity.copy()
        
        if 'Event Start Timestamp' not in df.columns:
            return pd.DataFrame()
        
        df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df.dropna(subset=['Event Start Timestamp'])
        
        if year:
            df = df[df['Event Start Timestamp'].dt.year == year]
        
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'PLAY_END']
        
        df['hour'] = df['Event Start Timestamp'].dt.hour
        
        hourly = df.groupby('hour').agg({
            'Song Name': 'count',
            'Play Duration Milliseconds': 'sum'
        }).rename(columns={
            'Song Name': 'play_count',
            'Play Duration Milliseconds': 'total_duration_ms'
        })
        
        # Fill missing hours with 0
        hourly = hourly.reindex(range(24), fill_value=0)
        hourly['total_duration_hours'] = (hourly['total_duration_ms'] / (1000 * 60 * 60)).round(2)
        hourly = hourly.reset_index().rename(columns={'index': 'hour'})
        
        return hourly
    
    def get_listening_by_day_of_week(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get listening activity grouped by day of week.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            DataFrame with daily listening stats (0=Monday, 6=Sunday)
        """
        if self.play_activity is None:
            return pd.DataFrame()
        
        df = self.play_activity.copy()
        
        if 'Event Start Timestamp' not in df.columns:
            return pd.DataFrame()
        
        df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df.dropna(subset=['Event Start Timestamp'])
        
        if year:
            df = df[df['Event Start Timestamp'].dt.year == year]
        
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'PLAY_END']
        
        df['day_of_week'] = df['Event Start Timestamp'].dt.dayofweek
        
        daily = df.groupby('day_of_week').agg({
            'Song Name': 'count',
            'Play Duration Milliseconds': 'sum'
        }).rename(columns={
            'Song Name': 'play_count',
            'Play Duration Milliseconds': 'total_duration_ms'
        })
        
        daily = daily.reindex(range(7), fill_value=0)
        daily['total_duration_hours'] = (daily['total_duration_ms'] / (1000 * 60 * 60)).round(2)
        daily = daily.reset_index().rename(columns={'index': 'day_of_week'})
        
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily['day_name'] = daily['day_of_week'].apply(lambda x: day_names[x])
        
        return daily
    
    def get_listening_streaks(self, year: Optional[int] = None) -> Dict:
        """
        Calculate listening streak statistics.
        Inspired by jcblsn/apple-music-wrapped.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            Dictionary with streak statistics
        """
        if self.play_activity is None:
            return {'longest_streak': 0, 'current_streak': 0, 'total_listening_days': 0}
        
        df = self.play_activity.copy()
        
        if 'Event Start Timestamp' not in df.columns:
            return {'longest_streak': 0, 'current_streak': 0, 'total_listening_days': 0}
        
        df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df.dropna(subset=['Event Start Timestamp'])
        
        if year:
            df = df[df['Event Start Timestamp'].dt.year == year]
        
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'PLAY_END']
        
        # Get unique dates with listening activity
        listening_dates = sorted(df['Event Start Timestamp'].dt.date.unique())
        
        if not listening_dates:
            return {'longest_streak': 0, 'current_streak': 0, 'total_listening_days': 0}
        
        # Calculate streaks
        longest_streak = 1
        current_streak = 1
        
        from datetime import timedelta
        
        for i in range(1, len(listening_dates)):
            if (listening_dates[i] - listening_dates[i-1]).days == 1:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 1
        
        return {
            'longest_streak': longest_streak,
            'current_streak': current_streak,
            'total_listening_days': len(listening_dates)
        }
    
    def get_diversity_score(self, year: Optional[int] = None) -> Dict:
        """
        Calculate music diversity/exploration metrics.
        Inspired by jcblsn/apple-music-wrapped.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            Dictionary with diversity metrics
        """
        stats = self.get_play_stats(year)
        top_songs = self.get_top_songs(100, year)
        top_artists = self.get_top_artists(100, year)
        
        unique_songs = stats['unique_songs']
        unique_artists = len(top_artists)
        total_plays = stats['total_plays']
        
        # Calculate various diversity metrics
        
        # Songs per artist ratio (higher = more diverse)
        songs_per_artist = unique_songs / max(unique_artists, 1)
        
        # Replay ratio (lower = more exploratory, higher = replay same songs)
        replay_ratio = total_plays / max(unique_songs, 1)
        
        # Top 10 concentration (what % of plays are top 10 songs)
        top_10_plays = top_songs.head(10)['play_count'].sum() if not top_songs.empty else 0
        top_10_concentration = (top_10_plays / max(total_plays, 1)) * 100
        
        # Diversity score (0-100, higher = more diverse)
        # Based on: low replay ratio + low top 10 concentration + high songs per artist
        diversity_score = min(100, max(0, 
            100 - (top_10_concentration * 0.5) - (replay_ratio * 5) + (songs_per_artist * 2)
        ))
        
        return {
            'diversity_score': round(diversity_score, 1),
            'songs_per_artist': round(songs_per_artist, 1),
            'replay_ratio': round(replay_ratio, 1),
            'top_10_concentration': round(top_10_concentration, 1),
            'unique_songs': unique_songs,
            'unique_artists': unique_artists
        }
    
    def get_peak_listening(self, year: Optional[int] = None) -> Dict:
        """
        Get peak listening times and dates.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            Dictionary with peak listening info
        """
        hourly = self.get_listening_by_hour(year)
        daily = self.get_listening_by_day_of_week(year)
        monthly = self.get_listening_by_month(year)
        
        result = {
            'peak_hour': None,
            'peak_hour_plays': 0,
            'peak_day': None,
            'peak_day_plays': 0,
            'peak_month': None,
            'peak_month_plays': 0
        }
        
        if not hourly.empty:
            peak_hour_row = hourly.loc[hourly['play_count'].idxmax()]
            result['peak_hour'] = int(peak_hour_row['hour'])
            result['peak_hour_plays'] = int(peak_hour_row['play_count'])
        
        if not daily.empty:
            peak_day_row = daily.loc[daily['play_count'].idxmax()]
            result['peak_day'] = peak_day_row['day_name']
            result['peak_day_plays'] = int(peak_day_row['play_count'])
        
        if not monthly.empty:
            peak_month_row = monthly.loc[monthly['play_count'].idxmax()]
            result['peak_month'] = peak_month_row['month']
            result['peak_month_plays'] = int(peak_month_row['play_count'])
        
        return result
    
    def get_summary(self, year: Optional[int] = None) -> Dict:
        """
        Get a complete summary of listening data.
        
        Args:
            year: Optional year to filter by
            
        Returns:
            Dictionary with complete listening summary
        """
        return {
            'stats': self.get_play_stats(year),
            'top_songs': self.get_top_songs(10, year).to_dict('records'),
            'top_artists': self.get_top_artists(10, year).to_dict('records'),
            'top_genres': self.get_top_genres(5, year).to_dict('records'),
            'monthly': self.get_listening_by_month(year).to_dict('records'),
            'hourly': self.get_listening_by_hour(year).to_dict('records'),
            'daily': self.get_listening_by_day_of_week(year).to_dict('records'),
            'streaks': self.get_listening_streaks(year),
            'diversity': self.get_diversity_score(year),
            'peak': self.get_peak_listening(year)
        }


def main():
    """Test the parser with sample data."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python apple_music_parser.py <path_to_apple_music_activity_folder>")
        sys.exit(1)
    
    data_dir = sys.argv[1]
    parser = AppleMusicParser(data_dir)
    
    print("\n" + "="*60)
    print("APPLE MUSIC LISTENING SUMMARY")
    print("="*60)
    
    # Get stats
    stats = parser.get_play_stats()
    print(f"\n📊 Overall Statistics:")
    print(f"   Total plays: {stats['total_plays']:,}")
    print(f"   Total listening time: {stats['total_listening_time_hours']} hours")
    print(f"   Unique songs: {stats['unique_songs']:,}")
    if stats['date_range']['start']:
        print(f"   Date range: {stats['date_range']['start']} to {stats['date_range']['end']}")
    
    # Top songs
    print(f"\n🎵 Top 10 Songs:")
    top_songs = parser.get_top_songs(10)
    for i, row in top_songs.iterrows():
        print(f"   {i+1}. {row['Song Name']} ({row['play_count']} plays)")
    
    # Top artists
    print(f"\n🎤 Top 10 Artists:")
    top_artists = parser.get_top_artists(10)
    for i, row in top_artists.iterrows():
        print(f"   {i+1}. {row['artist']} ({row['play_count']} plays)")
    
    # Top genres
    print(f"\n🎸 Top 5 Genres:")
    top_genres = parser.get_top_genres(5)
    for i, row in top_genres.iterrows():
        print(f"   {i+1}. {row['genre']}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()

