"""
Wrapped Image Generator

Generates Spotify Wrapped-style images from listening data.
Supports both Spotify and Apple Music data, with optional
memorial/tribute styling.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import urllib.request
from dataclasses import dataclass
from enum import Enum

from analytics import ListeningSummary, Platform


class WrappedStyle(Enum):
    """Available wrapped visual styles."""
    SPOTIFY_2021 = "spotify_2021"      # Original Spotify style
    SPOTIFY_2023 = "spotify_2023"      # Newer Spotify style  
    MEMORIAL = "memorial"               # Softer, tribute-appropriate style
    MINIMAL = "minimal"                 # Clean, minimal design


@dataclass
class ColorPalette:
    """Color palette for wrapped images."""
    primary: Tuple[int, int, int]
    secondary: Tuple[int, int, int]
    background: Tuple[int, int, int]
    text: Tuple[int, int, int]
    accent: Tuple[int, int, int]


# Predefined color palettes
PALETTES = {
    WrappedStyle.SPOTIFY_2021: ColorPalette(
        primary=(248, 215, 226),      # Pink text
        secondary=(211, 12, 45),       # Red accent
        background=(0, 0, 0),          # Black bg
        text=(248, 215, 226),
        accent=(29, 185, 84)           # Spotify green
    ),
    WrappedStyle.SPOTIFY_2023: ColorPalette(
        primary=(35, 50, 109),         # Navy text
        secondary=(153, 255, 153),     # Mint green
        background=(153, 255, 153),
        text=(35, 50, 109),
        accent=(255, 100, 100)
    ),
    WrappedStyle.MEMORIAL: ColorPalette(
        primary=(255, 255, 255),       # White text
        secondary=(180, 180, 200),     # Soft purple-gray
        background=(45, 45, 65),       # Deep purple-gray
        text=(255, 255, 255),
        accent=(200, 170, 140)         # Warm gold
    ),
    WrappedStyle.MINIMAL: ColorPalette(
        primary=(40, 40, 40),          # Dark gray text
        secondary=(100, 100, 100),
        background=(250, 250, 250),    # Off-white
        text=(40, 40, 40),
        accent=(80, 80, 80)
    )
}


class WrappedGenerator:
    """Generates wrapped-style images from listening data."""
    
    def __init__(self, output_dir: str = ".", 
                 style: WrappedStyle = WrappedStyle.MEMORIAL,
                 font_path: Optional[str] = None):
        """
        Initialize the generator.
        
        Args:
            output_dir: Directory to save generated images
            style: Visual style to use
            font_path: Path to custom font file
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.style = style
        self.palette = PALETTES[style]
        
        # Try to load fonts
        self.font_path = font_path or self._find_font()
        self._fonts = {}
    
    def _find_font(self) -> Optional[str]:
        """Find an available font file."""
        font_paths = [
            "font/Gotham.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        
        for path in font_paths:
            if Path(path).exists():
                return path
        return None
    
    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get or create a font at the specified size."""
        if size not in self._fonts:
            try:
                if self.font_path:
                    self._fonts[size] = ImageFont.truetype(self.font_path, size)
                else:
                    self._fonts[size] = ImageFont.load_default()
            except Exception:
                self._fonts[size] = ImageFont.load_default()
        return self._fonts[size]
    
    def _truncate_text(self, text: str, max_chars: int = 25) -> str:
        """Truncate text with ellipsis if too long."""
        if len(text) > max_chars:
            return text[:max_chars-3] + "..."
        return text
    
    def _download_image(self, url: str, save_path: str) -> bool:
        """Download an image from URL."""
        try:
            urllib.request.urlretrieve(url, save_path)
            return True
        except Exception as e:
            print(f"Warning: Could not download image: {e}")
            return False
    
    def _create_gradient_background(self, size: Tuple[int, int]) -> Image.Image:
        """Create a gradient background image."""
        img = Image.new('RGB', size, self.palette.background)
        draw = ImageDraw.Draw(img)
        
        # Create a subtle gradient overlay
        for y in range(size[1]):
            # Gradient from top to bottom
            factor = y / size[1]
            r = int(self.palette.background[0] * (1 - factor * 0.3))
            g = int(self.palette.background[1] * (1 - factor * 0.3))
            b = int(self.palette.background[2] * (1 - factor * 0.2))
            draw.line([(0, y), (size[0], y)], fill=(r, g, b))
        
        return img
    
    def generate_summary_card(self, summary: ListeningSummary, 
                             use_template: bool = False) -> str:
        """
        Generate the main summary card image.
        
        Args:
            summary: ListeningSummary object with listening data
            use_template: Whether to use existing template or generate new
            
        Returns:
            Path to the generated image
        """
        # Image dimensions (mobile-friendly)
        width, height = 1080, 1920
        
        if use_template and Path("templates/musics2021.jpg").exists():
            img = Image.open("templates/musics2021.jpg")
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        else:
            img = self._create_gradient_background((width, height))
        
        draw = ImageDraw.Draw(img)
        
        # Fonts
        title_font = self._get_font(72)
        heading_font = self._get_font(48)
        name_font = self._get_font(40)
        stat_font = self._get_font(36)
        
        # Header
        listener_name = summary.listener_name or "My"
        year_text = str(summary.year) if summary.year else ""
        platform_name = "Music" if summary.platform == Platform.APPLE_MUSIC else "Spotify"
        
        # Handle possessive properly
        if listener_name.lower() in ["my", "your"]:
            header_text = listener_name.title()
        elif listener_name.endswith('s'):
            header_text = f"{listener_name}'"
        else:
            header_text = f"{listener_name}'s"
        draw.text((80, 100), header_text, fill=self.palette.accent, font=title_font)
        
        subheader = f"{platform_name} Wrapped {year_text}"
        draw.text((80, 180), subheader, fill=self.palette.text, font=heading_font)
        
        # Stats section
        y_pos = 320
        
        # Listening time (big stat)
        hours = summary.total_listening_time_hours
        if hours >= 100:
            time_text = f"{hours:,.0f}"
        else:
            time_text = f"{hours:,.1f}"
        
        draw.text((80, y_pos), time_text, fill=self.palette.primary, font=self._get_font(120))
        draw.text((80, y_pos + 130), "hours listened", fill=self.palette.secondary, font=stat_font)
        
        y_pos += 220
        
        # Additional stats
        stats_text = [
            f"{summary.total_plays:,} songs played",
            f"{summary.unique_artists:,} different artists",
            f"{summary.unique_songs:,} unique tracks"
        ]
        
        for stat in stats_text:
            draw.text((80, y_pos), stat, fill=self.palette.text, font=stat_font)
            y_pos += 50
        
        # Top Artists section
        y_pos += 60
        draw.text((80, y_pos), "Top Artists", fill=self.palette.accent, font=heading_font)
        y_pos += 70
        
        for i, artist in enumerate(summary.top_artists[:5], 1):
            name = self._truncate_text(artist['name'], 30)
            draw.text((80, y_pos), f"{i}.", fill=self.palette.secondary, font=name_font)
            draw.text((130, y_pos), name, fill=self.palette.text, font=name_font)
            y_pos += 55
        
        # Top Songs section
        y_pos += 40
        draw.text((80, y_pos), "Top Songs", fill=self.palette.accent, font=heading_font)
        y_pos += 70
        
        for i, song in enumerate(summary.top_songs[:5], 1):
            name = self._truncate_text(song['name'], 30)
            draw.text((80, y_pos), f"{i}.", fill=self.palette.secondary, font=name_font)
            draw.text((130, y_pos), name, fill=self.palette.text, font=name_font)
            y_pos += 55
        
        # Top Genre
        if summary.top_genres:
            y_pos += 40
            draw.text((80, y_pos), "Top Genre", fill=self.palette.accent, font=heading_font)
            y_pos += 70
            genre_name = summary.top_genres[0]['name']
            draw.text((80, y_pos), genre_name, fill=self.palette.text, font=self._get_font(52))
        
        # Footer
        if summary.date_range_start:
            footer = f"{summary.date_range_start} - {summary.date_range_end}"
            draw.text((80, height - 100), footer, fill=self.palette.secondary, font=stat_font)
        
        # Save
        output_path = self.output_dir / f"wrapped_summary_{summary.listener_name or 'user'}.jpg"
        img.save(output_path, 'JPEG', quality=95)
        
        return str(output_path)
    
    def generate_top_songs_card(self, summary: ListeningSummary,
                                artwork_paths: Optional[Dict[str, str]] = None) -> str:
        """
        Generate a top songs card with album artwork.
        
        Args:
            summary: ListeningSummary object
            artwork_paths: Dict mapping song names to artwork file paths
            
        Returns:
            Path to the generated image
        """
        width, height = 1080, 1920
        
        if Path("templates/topsongs.jpg").exists() and self.style == WrappedStyle.SPOTIFY_2021:
            img = Image.open("templates/topsongs.jpg")
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        else:
            img = self._create_gradient_background((width, height))
        
        draw = ImageDraw.Draw(img)
        
        # Fonts
        title_font = self._get_font(64)
        song_font = self._get_font(42)
        artist_font = self._get_font(28)
        
        # Title
        name = summary.listener_name or "My"
        if name.lower() in ["my", "your"]:
            title = f"{name.title()} Top Songs"
        elif name.endswith('s'):
            title = f"{name}' Top Songs"
        else:
            title = f"{name}'s Top Songs"
        draw.text((80, 120), title, fill=self.palette.accent, font=title_font)
        
        # Song list with artwork
        y_pos = 280
        artwork_size = 180
        
        for i, song in enumerate(summary.top_songs[:5], 1):
            # Artwork placeholder/image
            artwork_x = 80
            artwork_y = y_pos
            
            # Try to load artwork
            artwork_loaded = False
            if artwork_paths and song['name'] in artwork_paths:
                try:
                    art_path = artwork_paths[song['name']]
                    if art_path and Path(art_path).exists():
                        artwork = Image.open(art_path)
                        artwork = artwork.resize((artwork_size, artwork_size), Image.Resampling.LANCZOS)
                        img.paste(artwork, (artwork_x, artwork_y))
                        artwork_loaded = True
                except Exception as e:
                    print(f"Warning: Could not load artwork: {e}")
            
            if not artwork_loaded:
                # Draw placeholder
                draw.rectangle(
                    [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                    fill=self.palette.secondary
                )
                # Add number
                num_font = self._get_font(80)
                draw.text((artwork_x + 60, artwork_y + 40), str(i), 
                         fill=self.palette.background, font=num_font)
            
            # Song info
            text_x = artwork_x + artwork_size + 30
            text_y = artwork_y + 30
            
            song_name = self._truncate_text(song['name'], 22)
            draw.text((text_x, text_y), song_name, fill=self.palette.text, font=song_font)
            
            # Play count
            plays = f"{song['play_count']} plays"
            draw.text((text_x, text_y + 50), plays, fill=self.palette.secondary, font=artist_font)
            
            if song.get('album'):
                album = self._truncate_text(song['album'], 25)
                draw.text((text_x, text_y + 85), album, fill=self.palette.secondary, font=artist_font)
            
            y_pos += artwork_size + 40
        
        # Save
        output_path = self.output_dir / f"wrapped_topsongs_{summary.listener_name or 'user'}.jpg"
        img.save(output_path, 'JPEG', quality=95)
        
        return str(output_path)
    
    def generate_top_artists_card(self, summary: ListeningSummary,
                                  artwork_paths: Optional[Dict[str, str]] = None) -> str:
        """
        Generate a top artists card with artist images.
        
        Args:
            summary: ListeningSummary object
            artwork_paths: Dict mapping artist names to image file paths
            
        Returns:
            Path to the generated image
        """
        width, height = 1080, 1920
        
        if Path("templates/topartist.jpg").exists() and self.style == WrappedStyle.SPOTIFY_2021:
            img = Image.open("templates/topartist.jpg")
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        else:
            img = self._create_gradient_background((width, height))
        
        draw = ImageDraw.Draw(img)
        
        # Fonts
        title_font = self._get_font(64)
        artist_font = self._get_font(42)
        stat_font = self._get_font(28)
        
        # Title
        name = summary.listener_name or "My"
        if name.lower() in ["my", "your"]:
            title = f"{name.title()} Top Artists"
        elif name.endswith('s'):
            title = f"{name}' Top Artists"
        else:
            title = f"{name}'s Top Artists"
        draw.text((80, 120), title, fill=self.palette.accent, font=title_font)
        
        # Artist list
        y_pos = 280
        artwork_size = 180
        
        for i, artist in enumerate(summary.top_artists[:5], 1):
            artwork_x = 80
            artwork_y = y_pos
            
            # Try to load artwork
            artwork_loaded = False
            if artwork_paths and artist['name'] in artwork_paths:
                try:
                    art_path = artwork_paths[artist['name']]
                    if art_path and Path(art_path).exists():
                        artwork = Image.open(art_path)
                        artwork = artwork.resize((artwork_size, artwork_size), Image.Resampling.LANCZOS)
                        # Make circular
                        mask = Image.new('L', (artwork_size, artwork_size), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.ellipse((0, 0, artwork_size, artwork_size), fill=255)
                        img.paste(artwork, (artwork_x, artwork_y), mask)
                        artwork_loaded = True
                except Exception as e:
                    print(f"Warning: Could not load artwork: {e}")
            
            if not artwork_loaded:
                # Draw circular placeholder
                draw.ellipse(
                    [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                    fill=self.palette.secondary
                )
                # Add number
                num_font = self._get_font(80)
                draw.text((artwork_x + 60, artwork_y + 40), str(i), 
                         fill=self.palette.background, font=num_font)
            
            # Artist info
            text_x = artwork_x + artwork_size + 30
            text_y = artwork_y + 40
            
            artist_name = self._truncate_text(artist['name'], 20)
            draw.text((text_x, text_y), artist_name, fill=self.palette.text, font=artist_font)
            
            # Stats
            plays = f"{artist['play_count']} plays"
            if artist.get('total_hours', 0) > 0:
                plays += f" • {artist['total_hours']:.1f} hours"
            draw.text((text_x, text_y + 55), plays, fill=self.palette.secondary, font=stat_font)
            
            y_pos += artwork_size + 40
        
        # Save
        output_path = self.output_dir / f"wrapped_topartists_{summary.listener_name or 'user'}.jpg"
        img.save(output_path, 'JPEG', quality=95)
        
        return str(output_path)
    
    def generate_all(self, summary: ListeningSummary,
                    fetch_artwork: bool = True) -> List[str]:
        """
        Generate all wrapped images.
        
        Args:
            summary: ListeningSummary object
            fetch_artwork: Whether to fetch artwork from APIs
            
        Returns:
            List of paths to generated images
        """
        paths = []
        
        # Fetch artwork if requested
        artwork = {}
        if fetch_artwork:
            try:
                from artwork_fetcher import ArtworkFetcher
                fetcher = ArtworkFetcher()
                
                print("Fetching artist artwork...")
                for artist in summary.top_artists[:5]:
                    name = artist['name']
                    path = fetcher.get_artist_image(name)
                    if path:
                        artwork[name] = path
                        print(f"  ✓ {name}")
                    else:
                        path = fetcher.create_placeholder_image(name, bg_color=self.palette.secondary)
                        artwork[name] = path
                        print(f"  ○ {name} (placeholder)")
            except Exception as e:
                print(f"Warning: Could not fetch artwork: {e}")
        
        # Generate images
        print("\nGenerating wrapped images...")
        
        paths.append(self.generate_summary_card(summary))
        print(f"  ✓ Summary card")
        
        paths.append(self.generate_top_songs_card(summary))
        print(f"  ✓ Top songs card")
        
        paths.append(self.generate_top_artists_card(summary, artwork))
        print(f"  ✓ Top artists card")
        
        print(f"\nGenerated {len(paths)} images!")
        return paths


def main():
    """Test the generator with sample data."""
    from analytics import ListeningSummary, Platform
    
    # Create sample summary
    summary = ListeningSummary(
        platform=Platform.APPLE_MUSIC,
        listener_name="Test User",
        year=2024,
        total_plays=5000,
        total_listening_time_hours=250.5,
        unique_songs=1500,
        unique_artists=300,
        date_range_start="2024-01-01",
        date_range_end="2024-12-01",
        top_songs=[
            {'name': 'Song 1', 'play_count': 150, 'album': 'Album 1'},
            {'name': 'Song 2', 'play_count': 120, 'album': 'Album 2'},
            {'name': 'Song 3', 'play_count': 100, 'album': 'Album 3'},
            {'name': 'Song 4', 'play_count': 90, 'album': 'Album 4'},
            {'name': 'Song 5', 'play_count': 80, 'album': 'Album 5'},
        ],
        top_artists=[
            {'name': 'Artist 1', 'play_count': 500, 'total_hours': 25.5},
            {'name': 'Artist 2', 'play_count': 400, 'total_hours': 20.0},
            {'name': 'Artist 3', 'play_count': 300, 'total_hours': 15.5},
            {'name': 'Artist 4', 'play_count': 200, 'total_hours': 10.0},
            {'name': 'Artist 5', 'play_count': 100, 'total_hours': 5.5},
        ],
        top_genres=[
            {'name': 'Rock', 'play_count': 1000},
            {'name': 'Alternative', 'play_count': 800},
            {'name': 'Metal', 'play_count': 600},
        ]
    )
    
    # Generate images
    generator = WrappedGenerator(style=WrappedStyle.MEMORIAL)
    paths = generator.generate_all(summary, fetch_artwork=False)
    
    print("\nGenerated images:")
    for path in paths:
        print(f"  - {path}")


if __name__ == "__main__":
    main()

