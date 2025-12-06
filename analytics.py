"""
Unified Analytics Engine

Provides a unified interface for analyzing music listening data
from both Spotify and Apple Music.
"""

import pandas as pd
from typing import Optional, Dict, List, Union
from dataclasses import dataclass, field
from enum import Enum


class Platform(Enum):
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"


@dataclass
class ListeningSummary:
    """Unified listening summary across platforms."""
    
    platform: Platform
    
    # Overall stats
    total_plays: int = 0
    total_listening_time_hours: float = 0.0
    unique_songs: int = 0
    unique_artists: int = 0
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    
    # Top content
    top_songs: List[Dict] = field(default_factory=list)
    top_artists: List[Dict] = field(default_factory=list)
    top_genres: List[Dict] = field(default_factory=list)
    top_albums: List[Dict] = field(default_factory=list)
    
    # Monthly breakdown
    monthly_stats: List[Dict] = field(default_factory=list)
    
    # Listener profile
    listener_name: Optional[str] = None
    year: Optional[int] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'platform': self.platform.value,
            'stats': {
                'total_plays': self.total_plays,
                'total_listening_time_hours': self.total_listening_time_hours,
                'unique_songs': self.unique_songs,
                'unique_artists': self.unique_artists,
                'date_range': {
                    'start': self.date_range_start,
                    'end': self.date_range_end
                }
            },
            'top_songs': self.top_songs,
            'top_artists': self.top_artists,
            'top_genres': self.top_genres,
            'top_albums': self.top_albums,
            'monthly_stats': self.monthly_stats,
            'listener_name': self.listener_name,
            'year': self.year
        }


class UnifiedAnalytics:
    """
    Unified analytics interface for Spotify and Apple Music data.
    """
    
    def __init__(self):
        self._apple_parser = None
        self._spotify_data = None
    
    def load_apple_music(self, data_dir: str,
                         exclude_artists: Optional[List[str]] = None,
                         exclude_songs: Optional[List[str]] = None,
                         exclude_genres: Optional[List[str]] = None) -> 'UnifiedAnalytics':
        """
        Load Apple Music data.
        
        Args:
            data_dir: Path to Apple Music Activity folder
            exclude_artists: List of artist names to exclude
            exclude_songs: List of song names to exclude
            exclude_genres: List of genres to exclude
            
        Returns:
            Self for method chaining
        """
        from apple_music_parser import AppleMusicParser
        self._apple_parser = AppleMusicParser(
            data_dir,
            exclude_artists=exclude_artists,
            exclude_songs=exclude_songs,
            exclude_genres=exclude_genres
        )
        return self
    
    def load_spotify(self, username: str = None, data_file: str = None) -> 'UnifiedAnalytics':
        """
        Load Spotify data.
        
        Args:
            username: Spotify username for API access
            data_file: Path to Spotify data export JSON
            
        Returns:
            Self for method chaining
        """
        # For now, we'll rely on the existing Spotify API integration
        # TODO: Add support for Spotify data export files
        self._spotify_data = {'username': username, 'data_file': data_file}
        return self
    
    def get_available_years(self) -> List[int]:
        """
        Get list of years with listening data.
        
        Returns:
            Sorted list of years
        """
        if self._apple_parser is None:
            return []
        
        years = set()
        
        if self._apple_parser.play_activity is not None:
            df = self._apple_parser.play_activity
            if 'Event Start Timestamp' in df.columns:
                dates = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
                years.update(dates.dropna().dt.year.unique())
        
        return sorted([int(y) for y in years if pd.notna(y)])
    
    def analyze_apple_music(self, year: Optional[int] = None, 
                           listener_name: Optional[str] = None) -> ListeningSummary:
        """
        Analyze Apple Music data and return unified summary.
        
        Args:
            year: Optional year to filter by
            listener_name: Name of the listener (for personalization)
            
        Returns:
            ListeningSummary object
        """
        if self._apple_parser is None:
            raise ValueError("Apple Music data not loaded. Call load_apple_music() first.")
        
        summary = ListeningSummary(
            platform=Platform.APPLE_MUSIC,
            listener_name=listener_name,
            year=year
        )
        
        # Get stats
        stats = self._apple_parser.get_play_stats(year)
        summary.total_plays = stats['total_plays']
        summary.total_listening_time_hours = stats['total_listening_time_hours']
        summary.unique_songs = stats['unique_songs']
        summary.date_range_start = stats['date_range']['start']
        summary.date_range_end = stats['date_range']['end']
        
        # Get top content
        top_songs_df = self._apple_parser.get_top_songs(10, year)
        summary.top_songs = self._normalize_songs(top_songs_df)
        
        top_artists_df = self._apple_parser.get_top_artists(10, year)
        summary.top_artists = self._normalize_artists(top_artists_df)
        summary.unique_artists = len(self._apple_parser.get_top_artists(1000, year))
        
        top_genres_df = self._apple_parser.get_top_genres(5, year)
        summary.top_genres = self._normalize_genres(top_genres_df)
        
        # Monthly stats
        monthly_df = self._apple_parser.get_listening_by_month(year)
        summary.monthly_stats = monthly_df.to_dict('records') if not monthly_df.empty else []
        
        return summary
    
    def _normalize_songs(self, df: pd.DataFrame) -> List[Dict]:
        """Normalize song data to unified format."""
        if df.empty:
            return []
        
        songs = []
        for _, row in df.iterrows():
            song = {
                'name': row.get('Song Name', row.get('name', 'Unknown')),
                'play_count': int(row.get('play_count', 0)),
                'album': row.get('Album Name', row.get('album', '')),
            }
            songs.append(song)
        return songs
    
    def _normalize_artists(self, df: pd.DataFrame) -> List[Dict]:
        """Normalize artist data to unified format."""
        if df.empty:
            return []
        
        artists = []
        for _, row in df.iterrows():
            artist = {
                'name': row.get('artist', row.get('name', 'Unknown')),
                'play_count': int(row.get('play_count', row.get('count', 0))),
                'total_hours': float(row.get('total_duration_hours', 0)),
            }
            artists.append(artist)
        return artists
    
    def _normalize_genres(self, df: pd.DataFrame) -> List[Dict]:
        """Normalize genre data to unified format."""
        if df.empty:
            return []
        
        genres = []
        for _, row in df.iterrows():
            genre = {
                'name': row.get('genre', row.get('name', 'Unknown')),
                'play_count': int(row.get('play_count', row.get('count', 0))),
            }
            genres.append(genre)
        return genres
    
    def print_summary(self, summary: ListeningSummary):
        """Print a formatted summary to console."""
        name = summary.listener_name or "Music"
        year_str = f" ({summary.year})" if summary.year else ""
        platform = "Apple Music" if summary.platform == Platform.APPLE_MUSIC else "Spotify"
        
        print("\n" + "="*70)
        print(f"🎵 {name}'s {platform} Wrapped{year_str}")
        print("="*70)
        
        # Stats
        print(f"\n📊 LISTENING STATS")
        print(f"   Total plays: {summary.total_plays:,}")
        print(f"   Total listening time: {summary.total_listening_time_hours:,.1f} hours")
        print(f"   That's {summary.total_listening_time_hours / 24:.1f} days of music!")
        print(f"   Unique songs: {summary.unique_songs:,}")
        print(f"   Unique artists: {summary.unique_artists:,}")
        if summary.date_range_start:
            print(f"   Period: {summary.date_range_start} to {summary.date_range_end}")
        
        # Top songs
        print(f"\n🎵 TOP SONGS")
        for i, song in enumerate(summary.top_songs[:5], 1):
            print(f"   {i}. {song['name']} ({song['play_count']} plays)")
        
        # Top artists
        print(f"\n🎤 TOP ARTISTS")
        for i, artist in enumerate(summary.top_artists[:5], 1):
            hours = f" - {artist['total_hours']:.1f}h" if artist.get('total_hours') else ""
            print(f"   {i}. {artist['name']} ({artist['play_count']} plays{hours})")
        
        # Top genres
        if summary.top_genres:
            print(f"\n🎸 TOP GENRES")
            for i, genre in enumerate(summary.top_genres[:5], 1):
                print(f"   {i}. {genre['name']}")
        
        print("\n" + "="*70)
        
        return summary


def analyze_apple_music_data(data_dir: str, 
                             year: Optional[int] = None,
                             listener_name: Optional[str] = None,
                             exclude_artists: Optional[List[str]] = None,
                             exclude_songs: Optional[List[str]] = None,
                             exclude_genres: Optional[List[str]] = None) -> ListeningSummary:
    """
    Convenience function to analyze Apple Music data.
    
    Args:
        data_dir: Path to Apple Music Activity folder
        year: Optional year to filter by
        listener_name: Name of the listener
        exclude_artists: List of artist names to exclude
        exclude_songs: List of song names to exclude
        exclude_genres: List of genres to exclude
        
    Returns:
        ListeningSummary object
    """
    analytics = UnifiedAnalytics()
    analytics.load_apple_music(
        data_dir,
        exclude_artists=exclude_artists,
        exclude_songs=exclude_songs,
        exclude_genres=exclude_genres
    )
    summary = analytics.analyze_apple_music(year, listener_name)
    analytics.print_summary(summary)
    return summary


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python analytics.py <path_to_apple_music_activity>")
        sys.exit(1)
    
    data_dir = sys.argv[1]
    year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    name = sys.argv[3] if len(sys.argv) > 3 else None
    
    analyze_apple_music_data(data_dir, year, name)

