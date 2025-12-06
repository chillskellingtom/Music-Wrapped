#!/usr/bin/env python3
"""
Music Wrapped - Universal Music Listening Summary Generator

Generate Spotify Wrapped-style summaries from Spotify or Apple Music data.

Usage:
    # Apple Music (from data export)
    python music_wrapped.py apple /path/to/Apple\ Music\ Activity --name "John" --year 2024
    
    # Spotify (using API)
    python music_wrapped.py spotify username --name "Jane"
    
    # Generate images only (after analysis)
    python music_wrapped.py generate /path/to/data --style memorial

Author: Extended from Spotify-Wrapped by Hossein Mohseni
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from analytics import UnifiedAnalytics, ListeningSummary, Platform
from wrapped_generator import WrappedGenerator, WrappedStyle


def analyze_apple_music(data_dir: str, 
                       name: Optional[str] = None,
                       year: Optional[int] = None,
                       all_years: bool = False,
                       by_year: bool = False,
                       output_dir: str = ".",
                       style: str = "memorial",
                       fetch_artwork: bool = False,
                       exclude_artists: Optional[list] = None,
                       exclude_songs: Optional[list] = None,
                       exclude_genres: Optional[list] = None) -> None:
    """
    Analyze Apple Music data and generate wrapped images.
    
    Args:
        data_dir: Path to Apple Music Activity folder
        name: Name of the listener
        year: Year to filter by (optional)
        all_years: Analyze all years combined (no year filter)
        by_year: Generate separate wrapped for each year
        output_dir: Directory to save generated images
        style: Visual style (spotify_2021, memorial, minimal)
        fetch_artwork: Whether to fetch artwork from internet
        exclude_artists: List of artist names to exclude
        exclude_songs: List of song names to exclude
        exclude_genres: List of genres to exclude
    """
    print(f"\n🎵 Music Wrapped - Apple Music Edition")
    print("="*50)
    
    # Check data directory exists
    if not Path(data_dir).exists():
        print(f"❌ Error: Data directory not found: {data_dir}")
        sys.exit(1)
    
    # Exclusions info
    if exclude_artists:
        print(f"🚫 Excluding artists: {', '.join(exclude_artists)}")
    if exclude_songs:
        print(f"🚫 Excluding songs: {', '.join(exclude_songs)}")
    if exclude_genres:
        print(f"🚫 Excluding genres: {', '.join(exclude_genres)}")
    
    # Analyze data
    print(f"\n📂 Loading data from: {data_dir}")
    
    analytics = UnifiedAnalytics()
    analytics.load_apple_music(
        data_dir,
        exclude_artists=exclude_artists,
        exclude_songs=exclude_songs,
        exclude_genres=exclude_genres
    )
    
    # Determine which years to process
    style_enum = WrappedStyle.MEMORIAL
    if style == "spotify_2021":
        style_enum = WrappedStyle.SPOTIFY_2021
    elif style == "spotify_2023":
        style_enum = WrappedStyle.SPOTIFY_2023
    elif style == "minimal":
        style_enum = WrappedStyle.MINIMAL
    
    all_paths = []
    
    if by_year:
        # Get available years from the data
        years = analytics.get_available_years()
        print(f"\n📅 Found data for years: {', '.join(map(str, years))}")
        
        for yr in years:
            print(f"\n{'='*50}")
            print(f"📆 Processing year: {yr}")
            print('='*50)
            
            year_output_dir = Path(output_dir) / str(yr)
            year_output_dir.mkdir(parents=True, exist_ok=True)
            
            summary = analytics.analyze_apple_music(year=yr, listener_name=name)
            analytics.print_summary(summary)
            
            generator = WrappedGenerator(output_dir=str(year_output_dir), style=style_enum)
            paths = generator.generate_all(summary, fetch_artwork=fetch_artwork)
            all_paths.extend(paths)
    else:
        # Single analysis (either specific year, all years, or default)
        filter_year = None if all_years else year
        
        summary = analytics.analyze_apple_music(year=filter_year, listener_name=name)
        analytics.print_summary(summary)
        
        generator = WrappedGenerator(output_dir=output_dir, style=style_enum)
        paths = generator.generate_all(summary, fetch_artwork=fetch_artwork)
        all_paths.extend(paths)
    
    print(f"\n✨ Generated {len(all_paths)} images:")
    for path in all_paths:
        print(f"   📷 {path}")
    
    print(f"\n🎉 Done! Share these images with the family.")


def analyze_spotify(username: str,
                   name: Optional[str] = None,
                   output_dir: str = ".",
                   style: str = "spotify_2021") -> None:
    """
    Analyze Spotify data using the API and generate wrapped images.
    
    Args:
        username: Spotify username
        name: Display name (defaults to username)
        output_dir: Directory to save generated images
        style: Visual style
    """
    print(f"\n🎵 Music Wrapped - Spotify Edition")
    print("="*50)
    
    # Use existing Spotify functionality
    try:
        from get_info import wrapped
        print(f"\n🔑 Authenticating with Spotify...")
        print(f"   Username: {username}")
        
        # Call existing wrapped function
        wrapped(username)
        
        print(f"\n✨ Spotify Wrapped images generated!")
        print(f"   Check: Spotify-Wrapped.jpg, Spotify-Wrapped2.jpg, Spotify-Wrapped3.jpg")
        
    except ImportError:
        print("❌ Error: Spotify integration requires API keys.")
        print("   Please set up keys.py with your Spotify credentials.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Music Wrapped - Generate Spotify Wrapped-style summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze Apple Music data
  python music_wrapped.py apple "/path/to/Apple Music Activity" --name "John"
  
  # Filter by year
  python music_wrapped.py apple "/path/to/data" --name "John" --year 2024
  
  # Analyze all years combined
  python music_wrapped.py apple "/path/to/data" --name "John" --all-years
  
  # Generate separate wrapped for each year
  python music_wrapped.py apple "/path/to/data" --name "John" --by-year
  
  # Exclude specific artists, songs, or genres
  python music_wrapped.py apple "/path/to/data" --exclude-artist "Slipknot" --exclude-artist "Nickelback"
  python music_wrapped.py apple "/path/to/data" --exclude-song "Baby Shark"
  python music_wrapped.py apple "/path/to/data" --exclude-genre "Country"
  
  # Use Spotify API
  python music_wrapped.py spotify your_username
  
  # Choose different visual styles
  python music_wrapped.py apple "/path/to/data" --style memorial
  python music_wrapped.py apple "/path/to/data" --style spotify_2021
  python music_wrapped.py apple "/path/to/data" --style minimal
  
  # Fetch album artwork (slower but prettier)
  python music_wrapped.py apple "/path/to/data" --artwork
"""
    )
    
    subparsers = parser.add_subparsers(dest='platform', help='Music platform')
    
    # Apple Music subcommand
    apple_parser = subparsers.add_parser('apple', help='Analyze Apple Music data export')
    apple_parser.add_argument('data_dir', 
                             help='Path to Apple Music Activity folder from data export')
    apple_parser.add_argument('--name', '-n', 
                             help='Name of the listener (for personalization)')
    apple_parser.add_argument('--year', '-y', type=int,
                             help='Filter to specific year')
    apple_parser.add_argument('--all-years', action='store_true',
                             help='Analyze all years combined (no year filter)')
    apple_parser.add_argument('--by-year', action='store_true',
                             help='Generate separate wrapped for each year in the data')
    apple_parser.add_argument('--output', '-o', default='.',
                             help='Output directory for generated images')
    apple_parser.add_argument('--style', '-s', 
                             choices=['memorial', 'spotify_2021', 'spotify_2023', 'minimal'],
                             default='memorial',
                             help='Visual style for generated images')
    apple_parser.add_argument('--artwork', '-a', action='store_true',
                             help='Fetch album artwork from internet (slower)')
    apple_parser.add_argument('--exclude-artist', action='append', dest='exclude_artists',
                             metavar='ARTIST', help='Exclude an artist (can be used multiple times)')
    apple_parser.add_argument('--exclude-song', action='append', dest='exclude_songs',
                             metavar='SONG', help='Exclude a song (can be used multiple times)')
    apple_parser.add_argument('--exclude-genre', action='append', dest='exclude_genres',
                             metavar='GENRE', help='Exclude a genre (can be used multiple times)')
    
    # Spotify subcommand
    spotify_parser = subparsers.add_parser('spotify', help='Analyze Spotify via API')
    spotify_parser.add_argument('username', help='Spotify username')
    spotify_parser.add_argument('--name', '-n',
                               help='Display name (defaults to username)')
    spotify_parser.add_argument('--output', '-o', default='.',
                               help='Output directory for generated images')
    spotify_parser.add_argument('--style', '-s',
                               choices=['spotify_2021', 'spotify_2023', 'memorial', 'minimal'],
                               default='spotify_2021',
                               help='Visual style for generated images')
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.platform is None:
        parser.print_help()
        sys.exit(1)
    
    # Route to appropriate function
    if args.platform == 'apple':
        analyze_apple_music(
            data_dir=args.data_dir,
            name=args.name,
            year=args.year,
            all_years=args.all_years,
            by_year=args.by_year,
            output_dir=args.output,
            style=args.style,
            fetch_artwork=args.artwork,
            exclude_artists=args.exclude_artists,
            exclude_songs=args.exclude_songs,
            exclude_genres=args.exclude_genres
        )
    elif args.platform == 'spotify':
        analyze_spotify(
            username=args.username,
            name=args.name or args.username,
            output_dir=args.output,
            style=args.style
        )


if __name__ == "__main__":
    main()

