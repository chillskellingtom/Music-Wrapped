"""
Video Generator for Music Wrapped

Creates animated video summaries from wrapped images with music.
Supports short (30s) and full (2-3 min) versions.

Requires: ffmpeg installed on system
Optional: librosa for chorus/hook detection
"""

import subprocess
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import random
import json
import shutil

# Optional librosa for chorus detection
try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


class AudioQuality:
    """Audio quality preference settings."""
    # Quality order: higher index = higher quality
    EXTENSIONS_BY_QUALITY = ['.ogg', '.mp3', '.aac', '.m4a', '.wav', '.flac']
    
    @classmethod
    def get_quality_rank(cls, extension: str) -> int:
        """Get quality rank for an extension (higher = better)."""
        ext = extension.lower()
        if ext in cls.EXTENSIONS_BY_QUALITY:
            return cls.EXTENSIONS_BY_QUALITY.index(ext)
        return -1  # Unknown format
    
    @classmethod
    def sort_by_quality(cls, files: List[Path], prefer_highest: bool = True) -> List[Path]:
        """Sort files by quality (highest first by default)."""
        return sorted(
            files,
            key=lambda f: cls.get_quality_rank(f.suffix),
            reverse=prefer_highest
        )


class ChorusDetector:
    """Detects the chorus/hook section of a song using audio analysis."""
    
    # Default fallback: skip intro (usually 20-45 seconds into song)
    DEFAULT_START_OFFSET = 30.0
    
    @classmethod
    def find_chorus_start(cls, audio_path: Path, duration: float = 30.0) -> float:
        """
        Find the best starting point for a song snippet (chorus/hook).
        
        Uses librosa to analyze the audio and find the most energetic
        or "exciting" section, which is typically the chorus.
        
        Args:
            audio_path: Path to the audio file
            duration: Duration of the clip we'll extract
            
        Returns:
            Start time in seconds for the best section
        """
        if not LIBROSA_AVAILABLE:
            # Fallback: skip intro
            return cls.DEFAULT_START_OFFSET
        
        try:
            # Load audio (only first 3 minutes to speed up analysis)
            y, sr = librosa.load(str(audio_path), duration=180, sr=22050)
            
            # Calculate energy/loudness over time
            # Using RMS energy in short windows
            hop_length = 512
            frame_length = 2048
            
            # Get RMS energy
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Get spectral centroid (brightness - choruses tend to be brighter)
            spectral_cent = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
            
            # Normalize both features
            rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-6)
            cent_norm = (spectral_cent - spectral_cent.min()) / (spectral_cent.max() - spectral_cent.min() + 1e-6)
            
            # Combined "excitement" score (energy + brightness)
            excitement = 0.7 * rms_norm + 0.3 * cent_norm
            
            # Smooth the excitement curve
            window_size = int(sr / hop_length * 2)  # 2 second window
            if window_size > 1:
                excitement_smooth = np.convolve(excitement, np.ones(window_size)/window_size, mode='same')
            else:
                excitement_smooth = excitement
            
            # Find the frame with maximum excitement
            # But avoid the very beginning (intro) and very end
            min_frame = int(15 * sr / hop_length)  # Skip first 15 seconds
            max_frame = len(excitement_smooth) - int(duration * sr / hop_length)
            
            if max_frame <= min_frame:
                return cls.DEFAULT_START_OFFSET
            
            # Find peak in the valid range
            valid_range = excitement_smooth[min_frame:max_frame]
            peak_frame = min_frame + np.argmax(valid_range)
            
            # Convert frame to time
            peak_time = librosa.frames_to_time(peak_frame, sr=sr, hop_length=hop_length)
            
            # Back up a bit before the peak to catch the start of the chorus
            start_time = max(0, peak_time - 5)
            
            return start_time
            
        except Exception as e:
            print(f"   ⚠️  Chorus detection failed: {e}")
            return cls.DEFAULT_START_OFFSET
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if chorus detection is available."""
        return LIBROSA_AVAILABLE


class VideoGenerator:
    """Generates wrapped video summaries with music."""
    
    # Spotify Wrapped timing (seconds per slide)
    SPOTIFY_SECONDS_PER_SLIDE = 8  # Official Wrapped uses ~8s per story slide
    SPOTIFY_TOTAL_SLIDES = 3       # Summary, Top Songs, Top Artists
    
    # Default positive/uplifting songs for in-memoriam endings
    SUGGESTED_CLOSING_SONGS = [
        "Here Comes the Sun",
        "What a Wonderful World",
        "Somewhere Over the Rainbow",
        "Three Little Birds",
        "Lean on Me",
        "You've Got a Friend",
        "Bridge Over Troubled Water",
        "Imagine",
        "Don't Stop Believin'",
        "Beautiful Day",
        "Walking on Sunshine",
        "I Will Remember You",
        "See You Again",
        "Time of Your Life",
        "My Way",
        "Wind Beneath My Wings",
        "Angels",
        "Hallelujah",
    ]
    
    # Supported audio extensions (searched in quality order by default)
    AUDIO_EXTENSIONS = ['.flac', '.wav', '.m4a', '.aac', '.mp3', '.ogg']
    
    # Supported subtitle extensions
    SUBTITLE_EXTENSIONS = ['.srt', '.vtt', '.ass', '.ssa']
    
    def __init__(self, 
                 output_dir: str = ".",
                 music_dir: str = "music",
                 temp_dir: str = ".video_temp",
                 prefer_high_quality: bool = True,
                 detect_chorus: bool = True):
        """
        Initialize video generator.
        
        Args:
            output_dir: Directory for output videos
            music_dir: Directory containing music files
            temp_dir: Temporary directory for processing
            prefer_high_quality: If True, prefer FLAC/WAV over MP3 (default True)
            detect_chorus: If True, use librosa to find the chorus/hook (default True)
        """
        self.output_dir = Path(output_dir)
        self.music_dir = Path(music_dir)
        self.temp_dir = Path(temp_dir)
        self.prefer_high_quality = prefer_high_quality
        self.detect_chorus = detect_chorus
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check ffmpeg is available
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Verify ffmpeg is installed."""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                   capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("ffmpeg not working properly")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Install with: brew install ffmpeg")
    
    def _find_music_file(self, song_name: str, artist: str = None, 
                         quality: str = "high") -> Optional[Path]:
        """
        Find a music file matching the song name, searching recursively.
        
        Searches for various naming patterns in all subdirectories:
        - song_name.mp3/flac/etc
        - artist - song_name.mp3/flac/etc
        - Partial matches containing song_name
        
        Args:
            song_name: Name of the song to find
            artist: Optional artist name for more specific matching
            quality: "high" (prefer FLAC/WAV), "low" (prefer MP3), or "any"
            
        Returns:
            Path to the best matching audio file, or None if not found
        """
        if not self.music_dir.exists():
            return None
        
        # Clean song name for matching
        clean_name = song_name.lower().strip()
        
        # Collect all matching files
        matches = []
        
        # Search recursively in all subdirectories
        for ext in self.AUDIO_EXTENSIONS:
            for f in self.music_dir.rglob(f"*{ext}"):
                # Skip files in 'closing' folder for main music search
                if 'closing' in f.parts:
                    continue
                    
                fname = f.stem.lower()
                
                # Check for matches (exact, artist-song, or partial)
                if fname == clean_name:
                    matches.append((f, 3))  # Exact match, highest priority
                elif artist and f"{artist.lower()} - {clean_name}" in fname:
                    matches.append((f, 2))  # Artist - Song match
                elif clean_name in fname:
                    matches.append((f, 1))  # Partial match
        
        if not matches:
            return None
        
        # Sort by match priority first, then by quality
        prefer_highest = (quality == "high") or (quality == "any" and self.prefer_high_quality)
        
        # Group by match priority
        best_priority = max(m[1] for m in matches)
        best_matches = [m[0] for m in matches if m[1] == best_priority]
        
        # Sort by quality and return the best one
        sorted_matches = AudioQuality.sort_by_quality(best_matches, prefer_highest)
        return sorted_matches[0] if sorted_matches else None
    
    def _find_subtitle_file(self, audio_path: Path) -> Optional[Path]:
        """
        Find a subtitle file matching an audio file.
        
        Looks for .srt, .vtt, .ass files with the same base name
        in the same directory as the audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Path to the subtitle file, or None if not found
        """
        if not audio_path:
            return None
            
        base_name = audio_path.stem
        parent_dir = audio_path.parent
        
        # Look for subtitle files with matching base name
        for ext in self.SUBTITLE_EXTENSIONS:
            # Try exact match first
            subtitle_path = parent_dir / f"{base_name}{ext}"
            if subtitle_path.exists():
                return subtitle_path
            
            # Try with language codes (e.g., .en.srt, .en-orig.srt)
            # Use iterdir instead of glob to avoid issues with special characters like [ ]
            try:
                for sub_file in parent_dir.iterdir():
                    if sub_file.suffix.lower() == ext.lower():
                        # Check if the subtitle filename starts with the audio base name
                        if sub_file.name.startswith(base_name):
                            return sub_file
            except OSError:
                continue
        
        return None
    
    def _find_closing_song(self, quality: str = "high") -> Optional[Path]:
        """
        Find a song from the closing folder for in-memoriam ending.
        
        Searches recursively in the closing folder and returns the
        highest quality version available.
        
        Args:
            quality: "high" (prefer FLAC/WAV), "low" (prefer MP3), or "any"
            
        Returns:
            Path to the closing song, or None if not found
        """
        closing_dir = self.music_dir / "closing"
        
        if not closing_dir.exists():
            return None
        
        songs = []
        
        # Search recursively for all audio files in closing folder
        for ext in self.AUDIO_EXTENSIONS:
            songs.extend(closing_dir.rglob(f"*{ext}"))
        
        if not songs:
            return None
        
        # Group songs by base name (to find different quality versions of same song)
        song_groups: Dict[str, List[Path]] = {}
        for song in songs:
            # Create a normalized name (remove extension and quality indicators)
            base = song.stem.lower()
            # Group by the core song name (strip common suffixes)
            for suffix in ['_hq', '_lq', ' (official video)', ' (audio)', ' [official video]']:
                base = base.replace(suffix, '')
            
            if base not in song_groups:
                song_groups[base] = []
            song_groups[base].append(song)
        
        # Pick a random song group
        random_group = random.choice(list(song_groups.values()))
        
        # Return the best quality version from that group
        prefer_highest = (quality == "high") or (quality == "any" and self.prefer_high_quality)
        sorted_songs = AudioQuality.sort_by_quality(random_group, prefer_highest)
        
        return sorted_songs[0] if sorted_songs else None
    
    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get duration of audio file in seconds."""
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except:
            return 30.0  # Default fallback
    
    def _create_image_video(self, image_path: Path, duration: float, 
                            output_path: Path, fade_in: float = 0.5,
                            fade_out: float = 0.5,
                            now_playing: Optional[Dict[str, str]] = None) -> bool:
        """
        Create a video clip from a single image with fade effects and optional Now Playing overlay.
        
        Args:
            image_path: Path to image
            duration: Duration in seconds
            output_path: Output video path
            fade_in: Fade in duration
            fade_out: Fade out duration
            now_playing: Optional dict with 'song' and 'artist' keys for overlay
        """
        # Build base filter chain
        filters = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            f"fade=t=in:st=0:d={fade_in}",
            f"fade=t=out:st={duration-fade_out}:d={fade_out}"
        ]
        
        # Add Now Playing text overlay if provided
        if now_playing and (now_playing.get('song') or now_playing.get('artist')):
            # Use system font - Roboto or fallback to Arial/Helvetica
            font_file = self._find_font_for_ffmpeg()
            
            # Escape special characters for ffmpeg drawtext
            song = self._escape_ffmpeg_text(now_playing.get('song', '').upper())
            artist = self._escape_ffmpeg_text(now_playing.get('artist', '').upper())
            
            # Position at bottom with padding, semi-transparent background box
            # White text, bold style
            y_base = 1750  # Near bottom of 1920px height
            
            # Build drawtext filter with proper escaping
            # Font path needs colons escaped and spaces handled
            font_escaped = font_file.replace(":", "\\:").replace(" ", "\\ ")
            
            if song:
                filters.append(
                    f"drawtext=text=SONG\\\\\\: {song}:fontfile={font_escaped}:"
                    f"fontsize=28:fontcolor=white:x=60:y={y_base}:"
                    f"box=1:boxcolor=black@0.5:boxborderw=8"
                )
            
            if artist:
                filters.append(
                    f"drawtext=text=ARTIST\\\\\\: {artist}:fontfile={font_escaped}:"
                    f"fontsize=28:fontcolor=white:x=60:y={y_base + 45}:"
                    f"box=1:boxcolor=black@0.5:boxborderw=8"
                )
        
        filter_str = ','.join(filters)
        
        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-i', str(image_path),
            '-vf', filter_str,
            '-c:v', 'libx264',
            '-t', str(duration),
            '-pix_fmt', 'yuv420p',
            '-r', '30',
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    def _find_font_for_ffmpeg(self) -> str:
        """Find a suitable font file for ffmpeg drawtext."""
        font_paths = [
            # Roboto (preferred)
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Roboto-Bold.ttf",
            "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
            # Fallbacks
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "font/Gotham.ttf",
        ]
        
        for path in font_paths:
            if Path(path).exists():
                return path
        
        # Last resort - return empty and let ffmpeg use default
        return ""
    
    def _escape_ffmpeg_text(self, text: str) -> str:
        """Escape special characters for ffmpeg drawtext filter."""
        if not text:
            return ""
        # Escape backslash, colon, apostrophe, brackets
        text = text.replace("\\", "\\\\")
        text = text.replace(":", "\\:")
        text = text.replace("'", "\\'")
        text = text.replace("[", "\\[")
        text = text.replace("]", "\\]")
        # Truncate if too long
        if len(text) > 40:
            text = text[:37] + "..."
        return text
    
    def _parse_song_info(self, audio_path: Path) -> Dict[str, str]:
        """
        Parse song and artist info from audio filename.
        
        Handles formats like:
        - "Artist - Song Title [VIDEO_ID].flac"
        - "Artist – Song Title (Official Video) [VIDEO_ID].mp3"
        - "Song Title [VIDEO_ID].flac" (no artist)
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict with 'song' and 'artist' keys
        """
        filename = audio_path.stem
        
        # Remove YouTube video ID pattern [xxxxx] from end
        import re
        filename = re.sub(r'\s*\[[^\]]+\]\s*$', '', filename)
        
        # Remove common video suffixes
        suffixes_to_remove = [
            '(Official Video)', '(Official Music Video)', '(Official Audio)',
            '(Visualizer)', '(Lyric Video)', '(Audio)', '(HD)', '(HQ)',
            '[Official Video]', '[Official Music Video]', '[Official Audio]',
        ]
        for suffix in suffixes_to_remove:
            filename = filename.replace(suffix, '')
        
        filename = filename.strip()
        
        # Try to split by common artist-title separators
        # Common separators: " - ", " – ", " — "
        separators = [' - ', ' – ', ' — ', ' | ']
        
        artist = ""
        song = filename  # Default to full filename as song
        
        for sep in separators:
            if sep in filename:
                parts = filename.split(sep, 1)
                artist = parts[0].strip()
                song = parts[1].strip() if len(parts) > 1 else ""
                break
        
        # Clean up extra whitespace
        artist = ' '.join(artist.split())
        song = ' '.join(song.split())
        
        return {'song': song, 'artist': artist}
    
    def _extract_audio_clip(self, audio_path: Path, output_path: Path,
                           start: float = 0, duration: float = 30,
                           fade_in: float = 1, fade_out: float = 2,
                           find_chorus: bool = False) -> bool:
        """
        Extract a clip from audio with fade effects.
        
        Args:
            audio_path: Source audio file
            output_path: Output audio path
            start: Start time in seconds (ignored if find_chorus=True)
            duration: Duration in seconds
            fade_in: Fade in duration
            fade_out: Fade out duration
            find_chorus: If True, use chorus detection to find best start point
        """
        # Find the best start time (chorus/hook)
        if find_chorus and self.detect_chorus:
            detected_start = ChorusDetector.find_chorus_start(audio_path, duration)
            if detected_start > 0:
                start = detected_start
                print(f"   🎯 Chorus detected at {start:.1f}s")
        
        # Audio filter for fades
        fade_filter = f"afade=t=in:st=0:d={fade_in},afade=t=out:st={duration-fade_out}:d={fade_out}"
        
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start),
            '-i', str(audio_path),
            '-t', str(duration),
            '-vn',  # No video (ignore embedded artwork)
            '-af', fade_filter,
            '-c:a', 'aac',
            '-b:a', '192k',
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    def _concatenate_videos(self, video_paths: List[Path], output_path: Path) -> bool:
        """Concatenate multiple video files."""
        # Create concat file
        concat_file = self.temp_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for vp in video_paths:
                f.write(f"file '{vp.absolute()}'\n")
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    def _merge_audio_video(self, video_path: Path, audio_path: Path,
                          output_path: Path, subtitle_path: Optional[Path] = None,
                          burn_subtitles: bool = False) -> bool:
        """
        Merge audio and video tracks, optionally with subtitles.
        
        Args:
            video_path: Input video file
            audio_path: Input audio file
            output_path: Output merged file
            subtitle_path: Optional subtitle file (.srt, .vtt, .ass)
            burn_subtitles: If True, burn subtitles into video (hardcode)
                           If False, embed as soft subtitles (can be toggled)
        
        Returns:
            True if successful, False otherwise
        """
        if subtitle_path and subtitle_path.exists():
            if burn_subtitles:
                # Burn subtitles into video (hardcoded)
                # Need to re-encode video with subtitles filter
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-vf', f"subtitles='{str(subtitle_path)}'",
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-shortest',
                    str(output_path)
                ]
            else:
                # Embed as soft subtitles (toggleable)
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-i', str(subtitle_path),
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-c:s', 'mov_text',  # Subtitle codec for MP4
                    '-metadata:s:s:0', 'language=eng',
                    '-shortest',
                    str(output_path)
                ]
        else:
            # No subtitles
            cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',
                str(output_path)
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    def _mix_audio_tracks(self, audio_paths: List[Path], durations: List[float],
                         output_path: Path, crossfade: float = 2) -> bool:
        """
        Mix multiple audio tracks with crossfade transitions.
        
        Args:
            audio_paths: List of audio file paths
            durations: Duration for each track
            output_path: Output mixed audio path
            crossfade: Crossfade duration between tracks
        """
        if len(audio_paths) == 1:
            # Single track, just copy with fade
            return self._extract_audio_clip(
                audio_paths[0], output_path,
                duration=durations[0], fade_in=1, fade_out=3
            )
        
        # Build complex filter for multiple tracks
        inputs = []
        filter_parts = []
        
        for i, (audio, dur) in enumerate(zip(audio_paths, durations)):
            inputs.extend(['-i', str(audio)])
            # Trim and fade each input
            filter_parts.append(f"[{i}:a]atrim=0:{dur},afade=t=in:d=1,afade=t=out:st={dur-2}:d=2[a{i}]")
        
        # Concatenate all
        concat_inputs = ''.join(f'[a{i}]' for i in range(len(audio_paths)))
        filter_parts.append(f"{concat_inputs}concat=n={len(audio_paths)}:v=0:a=1[out]")
        
        filter_complex = ';'.join(filter_parts)
        
        cmd = ['ffmpeg', '-y'] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[out]',
            '-c:a', 'aac',
            '-b:a', '192k',
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    def generate_short(self, image_paths: List[Path], 
                      song_names: List[str] = None,
                      output_name: str = "wrapped_short",
                      duration: int = None,
                      in_memoriam: bool = False,
                      include_subtitles: bool = False,
                      burn_subtitles: bool = False,
                      quality: str = "high",
                      spotify_style: bool = True,
                      find_chorus: bool = True) -> Optional[Path]:
        """
        Generate a short video (Spotify Wrapped style by default).
        
        Args:
            image_paths: List of wrapped image paths (3 images typical)
            song_names: List of song names to find audio for
            output_name: Output filename (without extension)
            duration: Total duration in seconds (auto-calculated if None)
            in_memoriam: If True, end with uplifting closing song (default False)
            include_subtitles: If True, include subtitles if available
            burn_subtitles: If True, hardcode subtitles into video
            quality: "high" (prefer FLAC/WAV), "low" (prefer MP3), or "any"
            spotify_style: If True, use official Spotify Wrapped timing (8s/slide)
            find_chorus: If True, detect and use the chorus/hook of the song
            
        Returns:
            Path to generated video or None if failed
        """
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            num_images = len(image_paths)
            
            # Calculate duration based on style
            if duration is None:
                if spotify_style:
                    time_per_image = self.SPOTIFY_SECONDS_PER_SLIDE  # 8 seconds
                    duration = num_images * time_per_image
                else:
                    time_per_image = 10  # Default fallback
                    duration = num_images * time_per_image
            else:
                time_per_image = duration / num_images
            
            style_name = "Spotify Wrapped" if spotify_style else "custom"
            print(f"🎬 Creating {duration}s video ({style_name} style)...")
            print(f"   {num_images} images × {time_per_image:.1f}s each")
            print(f"   Quality: {quality} | Chorus detection: {'on' if find_chorus else 'off'}")
            if include_subtitles:
                print(f"   Subtitles: {'burned in' if burn_subtitles else 'soft (toggleable)'}")
            
            # FIRST: Find audio files (one per slide for Spotify style)
            # We need this before creating video clips to add Now Playing overlay
            audio_paths_found = []
            now_playing_info = []  # List of {song, artist} dicts for each slide
            subtitle_path = None
            
            if song_names:
                # Try to find one song per slide (up to num_images songs)
                songs_needed = min(num_images, len(song_names))
                print(f"   🎵 Finding {songs_needed} songs (one per slide)...")
                
                for i, song in enumerate(song_names[:songs_needed]):
                    audio_path = self._find_music_file(song, quality=quality)
                    if audio_path:
                        audio_paths_found.append(audio_path)
                        # Parse song/artist from filename
                        song_info = self._parse_song_info(audio_path)
                        now_playing_info.append(song_info)
                        print(f"      {i+1}. {song_info.get('song', 'Unknown')[:35]}... ({audio_path.suffix.upper().strip('.')})")
                        # Get subtitles from first song only
                        if i == 0 and include_subtitles:
                            subtitle_path = self._find_subtitle_file(audio_path)
                            if subtitle_path:
                                print(f"      📝 Subtitles: {subtitle_path.name}")
                
                # If we didn't find enough songs, fill with what we have
                if not audio_paths_found:
                    # Fallback: try to find any song
                    for song in song_names:
                        audio_path = self._find_music_file(song, quality=quality)
                        if audio_path:
                            audio_paths_found.append(audio_path)
                            now_playing_info.append(self._parse_song_info(audio_path))
                            print(f"   🎵 Fallback: {audio_path.name}")
                            break
            
            # Pad now_playing_info to match num_images
            while len(now_playing_info) < num_images:
                if now_playing_info:
                    # Cycle through available songs
                    now_playing_info.append(now_playing_info[len(now_playing_info) % len(audio_paths_found)])
                else:
                    now_playing_info.append({})
            
            # Create video clips for each image WITH Now Playing overlay
            video_clips = []
            for i, img_path in enumerate(image_paths):
                clip_path = self.temp_dir / f"clip_{i}.mp4"
                print(f"   Creating clip {i+1}/{num_images}...")
                
                # Get the now playing info for this slide
                np_info = now_playing_info[i] if i < len(now_playing_info) else None
                
                if not self._create_image_video(img_path, time_per_image, clip_path, now_playing=np_info):
                    print(f"   ❌ Failed to create clip from {img_path}")
                    continue
                video_clips.append(clip_path)
            
            if not video_clips:
                print("❌ No video clips created")
                return None
            
            # Concatenate video clips
            concat_video = self.temp_dir / "concat.mp4"
            print("   Joining clips...")
            if not self._concatenate_videos(video_clips, concat_video):
                print("❌ Failed to concatenate videos")
                return None
            
            # Handle in-memoriam ending (optional, not Spotify default)
            closing_song = None
            if in_memoriam:
                closing_song = self._find_closing_song(quality=quality)
                if closing_song:
                    print(f"   💫 In memoriam closing: {closing_song.name} ({closing_song.suffix.upper().strip('.')})")
            
            # Generate final video
            output_path = self.output_dir / f"{output_name}.mp4"
            
            if audio_paths_found:
                audio_clip = self.temp_dir / "audio.m4a"
                print("   Adding music with crossfades...")
                
                # Calculate duration per song
                num_songs = len(audio_paths_found)
                
                if in_memoriam and closing_song:
                    # Reserve 30% for closing song
                    main_duration = duration * 0.7
                    closing_duration = duration * 0.3
                    duration_per_song = main_duration / num_songs
                else:
                    duration_per_song = duration / num_songs
                
                # Extract clips from each song (from chorus)
                extracted_clips = []
                for i, audio_path in enumerate(audio_paths_found):
                    clip_path = self.temp_dir / f"song_{i}.m4a"
                    print(f"      Extracting clip {i+1}/{num_songs}...")
                    self._extract_audio_clip(
                        audio_path, clip_path, 
                        duration=duration_per_song,
                        fade_in=0.5, fade_out=0.5,
                        find_chorus=find_chorus
                    )
                    extracted_clips.append(clip_path)
                
                # Add closing song if needed
                if in_memoriam and closing_song:
                    close_clip = self.temp_dir / "closing.m4a"
                    print(f"      Extracting closing song...")
                    self._extract_audio_clip(
                        closing_song, close_clip,
                        duration=closing_duration,
                        fade_in=0.5, fade_out=1.0,
                        find_chorus=find_chorus
                    )
                    extracted_clips.append(close_clip)
                
                # Mix all audio clips together
                if len(extracted_clips) > 1:
                    durations = [duration_per_song] * num_songs
                    if in_memoriam and closing_song:
                        durations.append(closing_duration)
                    self._mix_audio_tracks(extracted_clips, durations, audio_clip)
                else:
                    # Single song, just use it directly
                    shutil.copy(extracted_clips[0], audio_clip)
                
                self._merge_audio_video(
                    concat_video, audio_clip, output_path,
                    subtitle_path=subtitle_path if include_subtitles else None,
                    burn_subtitles=burn_subtitles
                )
            else:
                # No audio, just copy video
                shutil.copy(concat_video, output_path)
                print("   ⚠️  No audio found - video only")
            
            print(f"   ✅ Generated: {output_path}")
            return output_path
            
        finally:
            # Cleanup temp files
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
    
    def generate_full(self, image_paths: List[Path],
                     song_names: List[str] = None,
                     output_name: str = "wrapped_full",
                     in_memoriam: bool = False,
                     seconds_per_image: float = None,
                     include_subtitles: bool = False,
                     burn_subtitles: bool = False,
                     quality: str = "high",
                     spotify_style: bool = True,
                     find_chorus: bool = True) -> Optional[Path]:
        """
        Generate a full video with multiple songs.
        
        Args:
            image_paths: List of wrapped image paths
            song_names: List of song names for soundtrack
            output_name: Output filename
            in_memoriam: If True, end with uplifting closing song (default False)
            seconds_per_image: Time to show each image (auto if None)
            include_subtitles: If True, include subtitles if available
            burn_subtitles: If True, hardcode subtitles into video
            quality: "high" (prefer FLAC/WAV), "low" (prefer MP3), or "any"
            spotify_style: If True, use Spotify Wrapped timing
            find_chorus: If True, detect and use the chorus/hook
            
        Returns:
            Path to generated video
        """
        # Calculate duration
        if seconds_per_image is None:
            seconds_per_image = self.SPOTIFY_SECONDS_PER_SLIDE if spotify_style else 10
        
        total_duration = len(image_paths) * seconds_per_image
        
        # For full version, add extra time for closing if in_memoriam
        if in_memoriam:
            total_duration += 15  # Extra 15s for closing
        
        print(f"🎬 Creating full video ({total_duration:.0f}s)...")
        
        return self.generate_short(
            image_paths=image_paths,
            song_names=song_names,
            output_name=output_name,
            duration=int(total_duration),
            in_memoriam=in_memoriam,
            include_subtitles=include_subtitles,
            burn_subtitles=burn_subtitles,
            quality=quality,
            spotify_style=spotify_style,
            find_chorus=find_chorus
        )
    
    def list_available_music(self, show_quality: bool = True) -> Dict[str, List[Dict]]:
        """
        List all available music files, searching recursively.
        
        Args:
            show_quality: If True, include quality info for each file
            
        Returns:
            Dictionary with 'main' and 'closing' keys, each containing
            a list of song info dictionaries
        """
        result = {
            'main': [],
            'closing': [],
            'subtitles': []
        }
        
        if self.music_dir.exists():
            for ext in self.AUDIO_EXTENSIONS:
                for f in self.music_dir.rglob(f"*{ext}"):
                    # Check if it's in the closing folder
                    is_closing = 'closing' in f.parts
                    
                    song_info = {
                        'name': f.stem,
                        'path': str(f),
                        'format': f.suffix.upper().strip('.'),
                        'quality_rank': AudioQuality.get_quality_rank(f.suffix)
                    }
                    
                    # Check for subtitles
                    subtitle = self._find_subtitle_file(f)
                    if subtitle:
                        song_info['subtitle'] = str(subtitle)
                    
                    if is_closing:
                        result['closing'].append(song_info)
                    else:
                        result['main'].append(song_info)
        
        # Sort by name, then by quality (highest first)
        for key in ['main', 'closing']:
            result[key] = sorted(
                result[key],
                key=lambda x: (x['name'].lower(), -x['quality_rank'])
            )
        
        return result
    
    def list_available_music_simple(self) -> Dict[str, List[str]]:
        """
        List all available music files (simple format for backwards compatibility).
        
        Returns:
            Dictionary with 'main' and 'closing' keys containing filename lists
        """
        full_list = self.list_available_music()
        return {
            'main': [s['name'] + '.' + s['format'].lower() for s in full_list['main']],
            'closing': [s['name'] + '.' + s['format'].lower() for s in full_list['closing']]
        }


def main():
    """Test video generation and list available music."""
    import sys
    
    generator = VideoGenerator(
        output_dir="output/video",
        music_dir="music",
        prefer_high_quality=True
    )
    
    # List available music with quality info
    music = generator.list_available_music(show_quality=True)
    
    print("🎵 Available Music (searching recursively)")
    print("=" * 50)
    
    print(f"\n📀 Main songs: {len(music['main'])}")
    # Group by song name to show quality options
    seen_songs = set()
    for song in music['main']:
        if song['name'] not in seen_songs:
            # Find all versions of this song
            versions = [s for s in music['main'] if s['name'] == song['name']]
            formats = ', '.join(s['format'] for s in sorted(versions, key=lambda x: -x['quality_rank']))
            has_subs = any('subtitle' in s for s in versions)
            sub_indicator = " 📝" if has_subs else ""
            print(f"    - {song['name']} [{formats}]{sub_indicator}")
            seen_songs.add(song['name'])
    
    print(f"\n💫 Closing songs: {len(music['closing'])}")
    seen_songs = set()
    for song in music['closing']:
        if song['name'] not in seen_songs:
            versions = [s for s in music['closing'] if s['name'] == song['name']]
            formats = ', '.join(s['format'] for s in sorted(versions, key=lambda x: -x['quality_rank']))
            has_subs = any('subtitle' in s for s in versions)
            sub_indicator = " 📝" if has_subs else ""
            print(f"    - {song['name']} [{formats}]{sub_indicator}")
            seen_songs.add(song['name'])
    
    print("\n" + "=" * 50)
    print("📝 = Subtitles available")
    print("Quality order: FLAC > WAV > M4A > AAC > MP3 > OGG")


if __name__ == "__main__":
    main()

