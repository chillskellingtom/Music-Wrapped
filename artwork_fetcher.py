"""
Artwork Fetcher

Fetches album and artist artwork from MusicBrainz and Cover Art Archive.
Falls back to placeholder images when artwork is not available.
"""

import requests
import musicbrainzngs
from pathlib import Path
from typing import Optional, Dict, List
import time
import hashlib
import os

# Set up MusicBrainz client
musicbrainzngs.set_useragent(
    "MusicWrapped",
    "1.0",
    "https://github.com/music-wrapped"
)


class ArtworkFetcher:
    """Fetches artwork for artists and albums."""
    
    def __init__(self, cache_dir: str = ".artwork_cache"):
        """
        Initialize the artwork fetcher.
        
        Args:
            cache_dir: Directory to cache downloaded artwork
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._rate_limit_delay = 1.1  # MusicBrainz requires 1 req/sec
        self._last_request_time = 0
    
    def _rate_limit(self):
        """Ensure we don't exceed API rate limits."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _get_cache_path(self, identifier: str, type_: str = "artist") -> Path:
        """Get cache file path for an identifier."""
        # Create a safe filename from the identifier
        safe_name = hashlib.md5(identifier.encode()).hexdigest()
        return self.cache_dir / f"{type_}_{safe_name}.jpg"
    
    def _download_image(self, url: str, save_path: Path) -> bool:
        """
        Download an image from URL and save it.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(url, timeout=10, stream=True)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"Warning: Could not download image: {e}")
        return False
    
    def get_artist_image(self, artist_name: str) -> Optional[str]:
        """
        Get artist image URL or cached path.
        
        Tries multiple sources:
        1. Local cache
        2. MusicBrainz -> Fanart.tv / TheAudioDB
        
        Args:
            artist_name: Name of the artist
            
        Returns:
            Path to cached image or None if not found
        """
        cache_path = self._get_cache_path(artist_name, "artist")
        
        # Check cache first
        if cache_path.exists():
            return str(cache_path)
        
        self._rate_limit()
        
        try:
            # Search for artist on MusicBrainz
            result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
            
            if result['artist-list']:
                artist = result['artist-list'][0]
                artist_mbid = artist['id']
                
                # Try to get image from various sources
                # MusicBrainz doesn't host artist images directly,
                # but we can try Cover Art Archive for releases
                
                self._rate_limit()
                
                # Get artist's releases to find album art
                releases = musicbrainzngs.browse_releases(
                    artist=artist_mbid, 
                    limit=5,
                    release_type=['album']
                )
                
                if releases.get('release-list'):
                    for release in releases['release-list']:
                        release_mbid = release['id']
                        
                        # Try Cover Art Archive
                        caa_url = f"https://coverartarchive.org/release/{release_mbid}/front-250"
                        
                        try:
                            response = requests.head(caa_url, timeout=5, allow_redirects=True)
                            if response.status_code == 200:
                                if self._download_image(caa_url, cache_path):
                                    return str(cache_path)
                        except:
                            pass
                        
                        time.sleep(0.5)  # Be nice to the API
                
        except Exception as e:
            print(f"Warning: Could not fetch artist image for '{artist_name}': {e}")
        
        return None
    
    def get_album_artwork(self, artist_name: str, album_name: str) -> Optional[str]:
        """
        Get album artwork from Cover Art Archive.
        
        Args:
            artist_name: Name of the artist
            album_name: Name of the album
            
        Returns:
            Path to cached image or None if not found
        """
        cache_key = f"{artist_name}_{album_name}"
        cache_path = self._get_cache_path(cache_key, "album")
        
        # Check cache first
        if cache_path.exists():
            return str(cache_path)
        
        self._rate_limit()
        
        try:
            # Search for release on MusicBrainz
            query = f'artist:"{artist_name}" AND release:"{album_name}"'
            result = musicbrainzngs.search_releases(query=query, limit=1)
            
            if result['release-list']:
                release = result['release-list'][0]
                release_mbid = release['id']
                
                # Try Cover Art Archive
                caa_url = f"https://coverartarchive.org/release/{release_mbid}/front-250"
                
                try:
                    response = requests.head(caa_url, timeout=5, allow_redirects=True)
                    if response.status_code == 200:
                        if self._download_image(caa_url, cache_path):
                            return str(cache_path)
                except:
                    pass
                
        except Exception as e:
            print(f"Warning: Could not fetch album artwork for '{album_name}': {e}")
        
        return None
    
    def get_artwork_batch(self, items: List[Dict], type_: str = "artist") -> Dict[str, Optional[str]]:
        """
        Fetch artwork for multiple items.
        
        Args:
            items: List of dicts with 'artist' and optionally 'album' keys
            type_: 'artist' or 'album'
            
        Returns:
            Dictionary mapping item names to image paths
        """
        results = {}
        
        for item in items:
            if type_ == "artist":
                name = item.get('artist', '')
                if name:
                    results[name] = self.get_artist_image(name)
            elif type_ == "album":
                artist = item.get('artist', '')
                album = item.get('album', item.get('Album Name', ''))
                if artist and album:
                    key = f"{artist} - {album}"
                    results[key] = self.get_album_artwork(artist, album)
        
        return results
    
    def create_placeholder_image(self, text: str, size: tuple = (250, 250), 
                                  bg_color: tuple = (30, 30, 30),
                                  text_color: tuple = (255, 255, 255)) -> str:
        """
        Create a placeholder image with text.
        
        Args:
            text: Text to display (usually initials)
            size: Image size tuple (width, height)
            bg_color: Background color RGB tuple
            text_color: Text color RGB tuple
            
        Returns:
            Path to the created image
        """
        from PIL import Image, ImageDraw, ImageFont
        
        cache_path = self._get_cache_path(text, "placeholder")
        
        if cache_path.exists():
            return str(cache_path)
        
        # Create image
        img = Image.new('RGB', size, bg_color)
        draw = ImageDraw.Draw(img)
        
        # Get initials (first letters of each word, max 2)
        initials = ''.join(word[0].upper() for word in text.split()[:2] if word)
        if not initials:
            initials = text[:2].upper() if text else "?"
        
        # Try to use a nice font, fall back to default
        try:
            font = ImageFont.truetype("font/Gotham.ttf", size[0] // 3)
        except:
            try:
                # Try system fonts
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size[0] // 3)
            except:
                font = ImageFont.load_default()
        
        # Center text
        bbox = draw.textbbox((0, 0), initials, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2
        
        draw.text((x, y), initials, fill=text_color, font=font)
        
        img.save(cache_path, 'JPEG')
        return str(cache_path)


def main():
    """Test the artwork fetcher."""
    fetcher = ArtworkFetcher()
    
    # Test with some artists
    test_artists = ["David Bowie", "Puscifer", "Tool"]
    
    print("Testing artwork fetcher...")
    for artist in test_artists:
        print(f"\nFetching artwork for: {artist}")
        path = fetcher.get_artist_image(artist)
        if path:
            print(f"  ✓ Found: {path}")
        else:
            # Create placeholder
            path = fetcher.create_placeholder_image(artist)
            print(f"  ○ Created placeholder: {path}")


if __name__ == "__main__":
    main()

