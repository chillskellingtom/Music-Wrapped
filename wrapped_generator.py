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
    
    def _truncate_text(self, text, max_chars: int = 25) -> str:
        """Truncate text with ellipsis if too long."""
        # Handle None, NaN, or non-string types
        if text is None or (isinstance(text, float) and str(text) == 'nan'):
            return ""
        text = str(text)
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
                             use_template: bool = None) -> str:
        """
        Generate the main summary card image.
        
        Args:
            summary: ListeningSummary object with listening data
            use_template: Whether to use existing template (auto-detect if None)
            
        Returns:
            Path to the generated image
        """
        # Use template for spotify_2021 style by default
        if use_template is None:
            use_template = (self.style == WrappedStyle.SPOTIFY_2021)
        
        template_path = Path("templates/musics2021.jpg")
        
        if use_template and template_path.exists():
            # Use original template with original coordinates from hosseinhimself/Spotify-Wrapped
            img = Image.open(template_path)
            width, height = img.size  # Native: 1080x1946
            draw = ImageDraw.Draw(img)
            
            # Original fonts from get_info.py
            font = self._get_font(43)
            font2 = self._get_font(55)
            font3 = self._get_font(40)
            
            # Insert top artist image - original position: (245, 182), size: 600x600
            # This is the large square at the top of the template
            if summary.top_artists and summary.top_artists[0].get('image_path'):
                try:
                    artist_img_path = summary.top_artists[0]['image_path']
                    if Path(artist_img_path).exists():
                        artist_image = Image.open(artist_img_path)
                        artist_image = artist_image.resize((600, 600), Image.Resampling.LANCZOS)
                        img.paste(artist_image, (245, 182))
                except Exception as e:
                    print(f"   Warning: Could not load artist image: {e}")
            
            # Write top 5 artists (left column) - original position: (150, 1090)
            y_pos = 1090
            for artist in summary.top_artists[:5]:
                name = self._truncate_text(artist['name'], 16)
                draw.text((150, y_pos), name, (248, 215, 226), font=font)
                y_pos += 56
            
            # Write top 5 songs (right column) - original position: (640, 1090)
            y_pos = 1090
            for song in summary.top_songs[:5]:
                name = self._truncate_text(song['name'], 16)
                draw.text((640, y_pos), name, (248, 215, 226), font=font)
                y_pos += 56
            
            # Write top genre - original position: (560, 1510)
            if summary.top_genres:
                genre = summary.top_genres[0]['name'].capitalize()
                draw.text((560, 1510), genre, (248, 215, 226), font=font2)
            
            # Credit line - original position: (400, 1870)
            listener_name = summary.listener_name or "User"
            year_text = f" {summary.year}" if summary.year else ""
            draw.text((350, 1870), f"{listener_name}'s Wrapped{year_text}", (211, 12, 45), font=font3)
            
        else:
            # Procedural generation for other styles
            width, height = 1080, 1920
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
            
            if listener_name.lower() in ["my", "your"]:
                header_text = listener_name.title()
            elif listener_name.endswith('s'):
                header_text = f"{listener_name}'"
            else:
                header_text = f"{listener_name}'s"
            draw.text((80, 100), header_text, fill=self.palette.accent, font=title_font)
            
            subheader = f"{platform_name} Wrapped {year_text}"
            draw.text((80, 180), subheader, fill=self.palette.text, font=heading_font)
            
            y_pos = 320
            hours = summary.total_listening_time_hours
            time_text = f"{hours:,.0f}" if hours >= 100 else f"{hours:,.1f}"
            
            draw.text((80, y_pos), time_text, fill=self.palette.primary, font=self._get_font(120))
            draw.text((80, y_pos + 130), "hours listened", fill=self.palette.secondary, font=stat_font)
            y_pos += 220
            
            stats_text = [
                f"{summary.total_plays:,} songs played",
                f"{summary.unique_artists:,} different artists",
                f"{summary.unique_songs:,} unique tracks"
            ]
            for stat in stats_text:
                draw.text((80, y_pos), stat, fill=self.palette.text, font=stat_font)
                y_pos += 50
            
            y_pos += 60
            draw.text((80, y_pos), "Top Artists", fill=self.palette.accent, font=heading_font)
            y_pos += 70
            for i, artist in enumerate(summary.top_artists[:5], 1):
                name = self._truncate_text(artist['name'], 30)
                draw.text((80, y_pos), f"{i}.", fill=self.palette.secondary, font=name_font)
                draw.text((130, y_pos), name, fill=self.palette.text, font=name_font)
                y_pos += 55
            
            y_pos += 40
            draw.text((80, y_pos), "Top Songs", fill=self.palette.accent, font=heading_font)
            y_pos += 70
            for i, song in enumerate(summary.top_songs[:5], 1):
                name = self._truncate_text(song['name'], 30)
                draw.text((80, y_pos), f"{i}.", fill=self.palette.secondary, font=name_font)
                draw.text((130, y_pos), name, fill=self.palette.text, font=name_font)
                y_pos += 55
            
            if summary.top_genres:
                y_pos += 40
                draw.text((80, y_pos), "Top Genre", fill=self.palette.accent, font=heading_font)
                y_pos += 70
                genre_name = summary.top_genres[0]['name']
                draw.text((80, y_pos), genre_name, fill=self.palette.text, font=self._get_font(52))
            
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
        template_path = Path("templates/topsongs.jpg")
        use_template = (self.style == WrappedStyle.SPOTIFY_2021 and template_path.exists())
        
        if use_template:
            # Use original template with original coordinates from hosseinhimself/Spotify-Wrapped
            img = Image.open(template_path)
            width, height = img.size  # Native: 1080x1946
            draw = ImageDraw.Draw(img)
            
            # Original fonts and colors from get_info.py
            song_font = self._get_font(45)
            artist_font = self._get_font(30)
            
            # Original positions from get_info.py
            # Song names: (500, 600), artist names: (500, 680), album covers: (235, 533)
            # Each row increments by 235px for text, 238px for images
            
            y_text = 600
            y_artist = 650
            y_image = 533
            
            for i, song in enumerate(summary.top_songs[:5]):
                # Song name - original color: (0, 9, 5)
                song_name = self._truncate_text(song['name'], 16)
                draw.text((500, y_text), song_name, (0, 9, 5), font=song_font)
                
                # Artist name - original color: (72, 69, 60)
                # Note: We may not have artist in our data, use album or empty
                artist_text = ""
                if song.get('artist'):
                    artist_text = self._truncate_text(song['artist'], 16)
                draw.text((500, y_artist), artist_text, (72, 69, 60), font=artist_font)
                
                # Album cover placeholder (template already has numbered boxes)
                # Only paste if we have artwork
                if artwork_paths and song['name'] in artwork_paths:
                    try:
                        art_path = artwork_paths[song['name']]
                        if art_path and Path(art_path).exists():
                            artwork = Image.open(art_path)
                            artwork = artwork.resize((220, 220), Image.Resampling.LANCZOS)
                            img.paste(artwork, (235, y_image))
                    except Exception:
                        pass
                
                y_text += 235
                y_artist += 235
                y_image += 238
        else:
            # Procedural generation for other styles
            width, height = 1080, 1920
            img = self._create_gradient_background((width, height))
            draw = ImageDraw.Draw(img)
            
            title_font = self._get_font(64)
            song_font = self._get_font(42)
            artist_font = self._get_font(28)
            
            name = summary.listener_name or "My"
            if name.lower() in ["my", "your"]:
                title = f"{name.title()} Top Songs"
            elif name.endswith('s'):
                title = f"{name}' Top Songs"
            else:
                title = f"{name}'s Top Songs"
            draw.text((80, 120), title, fill=self.palette.accent, font=title_font)
            
            y_pos = 280
            artwork_size = 180
            
            for i, song in enumerate(summary.top_songs[:5], 1):
                artwork_x = 80
                artwork_y = y_pos
                
                artwork_loaded = False
                if artwork_paths and song['name'] in artwork_paths:
                    try:
                        art_path = artwork_paths[song['name']]
                        if art_path and Path(art_path).exists():
                            artwork = Image.open(art_path)
                            artwork = artwork.resize((artwork_size, artwork_size), Image.Resampling.LANCZOS)
                            img.paste(artwork, (artwork_x, artwork_y))
                            artwork_loaded = True
                    except Exception:
                        pass
                
                if not artwork_loaded:
                    draw.rectangle(
                        [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                        fill=self.palette.secondary
                    )
                    num_font = self._get_font(80)
                    draw.text((artwork_x + 60, artwork_y + 40), str(i), 
                             fill=self.palette.background, font=num_font)
                
                text_x = artwork_x + artwork_size + 30
                text_y = artwork_y + 30
                
                song_name = self._truncate_text(song['name'], 22)
                draw.text((text_x, text_y), song_name, fill=self.palette.text, font=song_font)
                
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
        template_path = Path("templates/topartist.jpg")
        use_template = (self.style == WrappedStyle.SPOTIFY_2021 and template_path.exists())
        
        if use_template:
            # Use original template with original coordinates from hosseinhimself/Spotify-Wrapped
            img = Image.open(template_path)
            width, height = img.size  # Native: 1080x1946
            draw = ImageDraw.Draw(img)
            
            # Original fonts and colors from get_info.py
            artist_font = self._get_font(45)
            
            # Original positions from get_info.py
            # Artist names: (500, 630), artist images: (235, 533)
            # Each row increments by 235px for text, 238px for images
            
            y_text = 630
            y_image = 533
            
            for i, artist in enumerate(summary.top_artists[:5]):
                # Artist name - original color: (35, 50, 109)
                artist_name = self._truncate_text(artist['name'], 16)
                draw.text((500, y_text), artist_name, (35, 50, 109), font=artist_font)
                
                # Artist image placeholder (template already has numbered boxes)
                # Only paste if we have artwork
                if artwork_paths and artist['name'] in artwork_paths:
                    try:
                        art_path = artwork_paths[artist['name']]
                        if art_path and Path(art_path).exists():
                            artwork = Image.open(art_path)
                            artwork = artwork.resize((220, 220), Image.Resampling.LANCZOS)
                            img.paste(artwork, (235, y_image))
                    except Exception:
                        pass
                
                y_text += 235
                y_image += 238
        else:
            # Procedural generation for other styles
            width, height = 1080, 1920
            img = self._create_gradient_background((width, height))
            draw = ImageDraw.Draw(img)
            
            title_font = self._get_font(64)
            artist_font = self._get_font(42)
            stat_font = self._get_font(28)
            
            name = summary.listener_name or "My"
            if name.lower() in ["my", "your"]:
                title = f"{name.title()} Top Artists"
            elif name.endswith('s'):
                title = f"{name}' Top Artists"
            else:
                title = f"{name}'s Top Artists"
            draw.text((80, 120), title, fill=self.palette.accent, font=title_font)
            
            y_pos = 280
            artwork_size = 180
            
            for i, artist in enumerate(summary.top_artists[:5], 1):
                artwork_x = 80
                artwork_y = y_pos
                
                artwork_loaded = False
                if artwork_paths and artist['name'] in artwork_paths:
                    try:
                        art_path = artwork_paths[artist['name']]
                        if art_path and Path(art_path).exists():
                            artwork = Image.open(art_path)
                            artwork = artwork.resize((artwork_size, artwork_size), Image.Resampling.LANCZOS)
                            mask = Image.new('L', (artwork_size, artwork_size), 0)
                            mask_draw = ImageDraw.Draw(mask)
                            mask_draw.ellipse((0, 0, artwork_size, artwork_size), fill=255)
                            img.paste(artwork, (artwork_x, artwork_y), mask)
                            artwork_loaded = True
                    except Exception:
                        pass
                
                if not artwork_loaded:
                    draw.ellipse(
                        [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                        fill=self.palette.secondary
                    )
                    num_font = self._get_font(80)
                    draw.text((artwork_x + 60, artwork_y + 40), str(i), 
                             fill=self.palette.background, font=num_font)
                
                text_x = artwork_x + artwork_size + 30
                text_y = artwork_y + 40
                
                artist_name = self._truncate_text(artist['name'], 20)
                draw.text((text_x, text_y), artist_name, fill=self.palette.text, font=artist_font)
                
                plays = f"{artist['play_count']} plays"
                if artist.get('total_hours', 0) > 0:
                    plays += f" • {artist['total_hours']:.1f} hours"
                draw.text((text_x, text_y + 55), plays, fill=self.palette.secondary, font=stat_font)
                
                y_pos += artwork_size + 40
        
        # Save
        output_path = self.output_dir / f"wrapped_topartists_{summary.listener_name or 'user'}.jpg"
        img.save(output_path, 'JPEG', quality=95)
        
        return str(output_path)
    
    def generate_insights_card(self, summary: ListeningSummary) -> str:
        """
        Generate an insights card with extended statistics.
        Inspired by jcblsn/apple-music-wrapped.
        
        Shows: peak listening times, streaks, diversity metrics.
        
        Args:
            summary: ListeningSummary object
            
        Returns:
            Path to the generated image
        """
        width, height = 1080, 1920
        
        # Use gradient background matching style
        img = self._create_gradient_background((width, height))
        draw = ImageDraw.Draw(img)
        
        # Fonts
        title_font = self._get_font(64)
        heading_font = self._get_font(42)
        value_font = self._get_font(72)
        label_font = self._get_font(28)
        
        # Header
        name = summary.listener_name or "Your"
        if name.lower() in ["my", "your"]:
            title = f"{name.title()} Listening Insights"
        elif name.endswith('s'):
            title = f"{name}' Insights"
        else:
            title = f"{name}'s Insights"
        
        draw.text((80, 100), title, fill=self.palette.accent, font=title_font)
        
        year_text = str(summary.year) if summary.year else ""
        if year_text:
            draw.text((80, 180), year_text, fill=self.palette.secondary, font=heading_font)
        
        y_pos = 280
        
        # Peak Listening Times Section
        draw.text((80, y_pos), "⏰ Peak Listening", fill=self.palette.accent, font=heading_font)
        y_pos += 70
        
        # Peak hour with emoji
        if summary.peak_hour is not None:
            hour = summary.peak_hour
            hour_str = f"{hour:02d}:00"
            if hour < 6:
                emoji = "🌙"
                desc = "Night owl"
            elif hour < 12:
                emoji = "☀️"
                desc = "Morning vibes"
            elif hour < 18:
                emoji = "🌤️"
                desc = "Afternoon"
            else:
                emoji = "🌆"
                desc = "Evening"
            
            draw.text((100, y_pos), f"{emoji} {hour_str}", fill=self.palette.text, font=value_font)
            draw.text((100, y_pos + 75), f"Your peak listening hour • {desc}", fill=self.palette.secondary, font=label_font)
            y_pos += 130
        
        # Peak day
        if summary.peak_day:
            draw.text((100, y_pos), f"📅 {summary.peak_day}s", fill=self.palette.text, font=heading_font)
            draw.text((100, y_pos + 50), "Your most musical day of the week", fill=self.palette.secondary, font=label_font)
            y_pos += 120
        
        # Streaks Section
        y_pos += 30
        draw.text((80, y_pos), "🔥 Listening Streaks", fill=self.palette.accent, font=heading_font)
        y_pos += 70
        
        if summary.longest_streak > 0:
            draw.text((100, y_pos), f"{summary.longest_streak}", fill=self.palette.text, font=value_font)
            draw.text((100, y_pos + 75), "Day listening streak (your longest!)", fill=self.palette.secondary, font=label_font)
            y_pos += 130
        
        if summary.total_listening_days > 0:
            draw.text((100, y_pos), f"{summary.total_listening_days}", fill=self.palette.text, font=heading_font)
            draw.text((100, y_pos + 50), "Total days with music", fill=self.palette.secondary, font=label_font)
            y_pos += 120
        
        # Diversity Section
        y_pos += 30
        draw.text((80, y_pos), "🎲 Music Diversity", fill=self.palette.accent, font=heading_font)
        y_pos += 70
        
        if summary.diversity_score > 0:
            # Draw diversity score as a visual bar
            score = summary.diversity_score
            draw.text((100, y_pos), f"{score:.0f}/100", fill=self.palette.text, font=value_font)
            
            # Progress bar
            bar_width = 400
            bar_height = 20
            bar_x = 100
            bar_y = y_pos + 80
            
            # Background bar
            draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], 
                          fill=self.palette.secondary)
            # Filled bar
            filled_width = int(bar_width * (score / 100))
            draw.rectangle([(bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height)], 
                          fill=self.palette.accent)
            
            # Diversity description
            if score >= 70:
                desc = "Musical explorer 🌍"
            elif score >= 40:
                desc = "Eclectic taste 🎭"
            else:
                desc = "You know what you like 💎"
            draw.text((100, bar_y + 35), desc, fill=self.palette.text, font=label_font)
            y_pos += 160
        
        # Additional metrics
        if summary.replay_ratio > 0:
            draw.text((100, y_pos), f"{summary.replay_ratio:.1f}×", fill=self.palette.text, font=heading_font)
            draw.text((100, y_pos + 50), "Average replays per song", fill=self.palette.secondary, font=label_font)
            y_pos += 100
        
        if summary.songs_per_artist > 0:
            draw.text((100, y_pos), f"{summary.songs_per_artist:.1f}", fill=self.palette.text, font=heading_font)
            draw.text((100, y_pos + 50), "Songs per artist average", fill=self.palette.secondary, font=label_font)
        
        # Attribution footer
        draw.text((80, height - 100), "Stats inspired by jcblsn/apple-music-wrapped", 
                 fill=self.palette.secondary, font=self._get_font(20))
        
        # Save
        output_path = self.output_dir / f"wrapped_insights_{summary.listener_name or 'user'}.jpg"
        img.save(output_path, 'JPEG', quality=95)
        
        return str(output_path)
    
    def generate_all(self, summary: ListeningSummary,
                    fetch_artwork: bool = True,
                    include_insights: bool = True) -> List[str]:
        """
        Generate all wrapped images.
        
        Args:
            summary: ListeningSummary object
            fetch_artwork: Whether to fetch artwork from APIs
            include_insights: Whether to include the insights card (4th slide)
            
        Returns:
            List of paths to generated images
        """
        paths = []
        
        # Fetch artwork if requested
        artist_artwork = {}
        song_artwork = {}
        
        if fetch_artwork:
            try:
                from artwork_fetcher import ArtworkFetcher
                fetcher = ArtworkFetcher()
                
                print("Fetching artist artwork...")
                for artist in summary.top_artists[:5]:
                    name = artist['name']
                    path = fetcher.get_artist_image(name)
                    if path:
                        artist_artwork[name] = path
                        # Store path in artist dict for summary card
                        artist['image_path'] = path
                        print(f"  ✓ {name}")
                    else:
                        path = fetcher.create_placeholder_image(name, bg_color=self.palette.secondary)
                        artist_artwork[name] = path
                        artist['image_path'] = path
                        print(f"  ○ {name} (placeholder)")
                
                # Also fetch song/album artwork and artist names
                print("\nFetching song artwork...")
                for song in summary.top_songs[:5]:
                    song_name = song['name']
                    album_name = song.get('album', '')
                    
                    # If song doesn't have artist, try to look it up from album
                    if not song.get('artist') and album_name:
                        looked_up_artist = fetcher.get_artist_for_album(album_name)
                        if looked_up_artist:
                            song['artist'] = looked_up_artist
                    
                    # Use the song's artist or fall back to top artist
                    artist_name = song.get('artist') or (summary.top_artists[0]['name'] if summary.top_artists else "")
                    
                    # Try album artwork first
                    path = None
                    
                    if album_name and artist_name:
                        path = fetcher.get_album_artwork(artist_name, album_name)
                    
                    # If no album art, try the artist's image as fallback
                    if not path and artist_name:
                        path = artist_artwork.get(artist_name)
                    
                    if path:
                        song_artwork[song_name] = path
                        song['artwork_path'] = path
                        artist_info = f" ({song.get('artist', '')[:15]})" if song.get('artist') else ""
                        print(f"  ✓ {song_name[:25]}{artist_info}")
                    else:
                        path = fetcher.create_placeholder_image(song_name, bg_color=self.palette.secondary)
                        song_artwork[song_name] = path
                        song['artwork_path'] = path
                        print(f"  ○ {song_name[:30]} (placeholder)")
                        
            except Exception as e:
                print(f"Warning: Could not fetch artwork: {e}")
        
        # Generate images
        print("\nGenerating wrapped images...")
        
        paths.append(self.generate_summary_card(summary))
        print(f"  ✓ Summary card")
        
        paths.append(self.generate_top_artists_card(summary, artist_artwork))
        print(f"  ✓ Top artists card")
        
        paths.append(self.generate_top_songs_card(summary, song_artwork))
        print(f"  ✓ Top songs card")
        
        # Include insights card (4th slide) with extended stats
        if include_insights and (summary.peak_hour is not None or summary.longest_streak > 0):
            paths.append(self.generate_insights_card(summary))
            print(f"  ✓ Insights card (inspired by jcblsn/apple-music-wrapped)")
        
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

