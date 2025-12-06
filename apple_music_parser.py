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
    
    @property
    def daily_tracks(self) -> Optional[pd.DataFrame]:
        """Lazy load and return daily tracks data."""
        if self._daily_tracks is None:
            self._daily_tracks = self._load_csv("Apple Music - Play History Daily Tracks.csv")
        return self._daily_tracks
    
    @property
    def track_history(self) -> Optional[pd.DataFrame]:
        """Lazy load and return track play history."""
        if self._track_history is None:
            self._track_history = self._load_csv("Apple Music - Track Play History.csv")
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
            'monthly': self.get_listening_by_month(year).to_dict('records')
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

