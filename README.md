# Music Wrapped 🎵

Generate beautiful Spotify Wrapped-style listening summaries from **Spotify** or **Apple Music** data.

Originally [Spotify-Wrapped by Hossein Mohseni](https://github.com/hosseinmh1/Spotify-Wrapped), extended to support Apple Music data exports with multiple visual styles including a softer "memorial" theme.

## Features

- 📊 **Apple Music Support**: Analyze your Apple Music listening history from data exports
- 🎧 **Spotify Support**: Connect via API to get your top tracks and artists
- 🎨 **Multiple Visual Styles**: Choose from Spotify 2021, Spotify 2023, Memorial, or Minimal themes
- 📈 **Detailed Analytics**: Top songs, artists, genres, total listening time, and more
- 🖼️ **Shareable Images**: Generate mobile-friendly images perfect for sharing
- 📅 **Year-by-Year Analysis**: Generate wrapped for each year separately with `--by-year`
- 🚫 **Exclusion Filters**: Hide specific artists, songs, or genres from results

---

## 📥 How to Get Your Music Data

### Apple Music

1. **Request your data from Apple:**
   - Go to [Apple's Data and Privacy portal](https://privacy.apple.com/)
   - Sign in with the Apple ID associated with the Apple Music account
   - Click **"Request a copy of your data"**
   - Select **"Apple Media Services information"** (this includes Apple Music)
   - Submit the request

2. **Wait for the download:**
   - Apple will send an email when your data is ready (usually 1-7 days)
   - Download and extract the ZIP file

3. **Locate the Apple Music Activity folder:**
   ```
   Apple Media Services information/
   └── Apple_Media_Services/
       └── Apple Music Activity/          ← Use this folder
           ├── Apple Music Play Activity.csv
           ├── Apple Music Library Tracks.json
           └── ... (other files)
   ```

### Spotify

**Option 1: Via Spotify API (Real-time)**
1. Create a Spotify Developer account at [developer.spotify.com](https://developer.spotify.com/)
2. Create a new app to get your `client_id` and `client_secret`
3. Set up `keys.py`:
   ```python
   client_id = "your_client_id"
   client_secret = "your_client_secret"
   redirect_uri = "http://localhost:8888/callback"
   ```

**Option 2: Request Data Export**
1. Go to [Spotify Privacy Settings](https://www.spotify.com/account/privacy/)
2. Scroll to "Download your data"
3. Request your data (takes up to 30 days)
4. Download and extract the ZIP file

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Clone and enter the repo
git clone https://github.com/yourusername/Music-Wrapped.git
cd Music-Wrapped

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Analyze Apple Music

```bash
# Basic usage
python music_wrapped.py apple "/path/to/Apple Music Activity"

# With personalization
python music_wrapped.py apple "/path/to/Apple Music Activity" --name "John"

# Filter by specific year
python music_wrapped.py apple "/path/to/data" --name "John" --year 2024

# Analyze all years combined
python music_wrapped.py apple "/path/to/data" --name "John" --all-years

# Generate separate wrapped for each year
python music_wrapped.py apple "/path/to/data" --name "John" --by-year
```

### 3. Exclude Content

```bash
# Exclude specific artists
python music_wrapped.py apple "/path/to/data" --exclude-artist "Nickelback"

# Exclude multiple artists
python music_wrapped.py apple "/path/to/data" --exclude-artist "Artist1" --exclude-artist "Artist2"

# Exclude specific songs
python music_wrapped.py apple "/path/to/data" --exclude-song "Baby Shark"

# Exclude genres
python music_wrapped.py apple "/path/to/data" --exclude-genre "Country"

# Combine exclusions
python music_wrapped.py apple "/path/to/data" \
  --exclude-artist "Slipknot" \
  --exclude-song "Annoying Song" \
  --exclude-genre "Polka"
```

### 4. Spotify Analysis

```bash
# Requires Spotify API credentials in keys.py
python music_wrapped.py spotify your_username
```

---

## 🎨 Visual Styles

| Style | Description | Best For |
|-------|-------------|----------|
| `memorial` | Soft purple-gray with gold accents | Tributes, memorials, gentle sharing |
| `spotify_2021` | Classic pink/black Spotify theme | Traditional Wrapped look |
| `spotify_2023` | Modern mint green Spotify style | Fresh, contemporary look |
| `minimal` | Clean black and white | Professional, understated |

```bash
python music_wrapped.py apple "/path/to/data" --style memorial
python music_wrapped.py apple "/path/to/data" --style spotify_2021
python music_wrapped.py apple "/path/to/data" --style minimal
```

---

## 📊 Output

The tool generates 3 images per analysis:

| Image | Contents |
|-------|----------|
| `wrapped_summary_{name}.jpg` | Total hours, play count, top artists, top songs, top genre |
| `wrapped_topsongs_{name}.jpg` | Top 5 songs with play counts and album names |
| `wrapped_topartists_{name}.jpg` | Top 5 artists with play counts and listening hours |

### Example Console Output

```
======================================================================
🎵 John's Apple Music Wrapped (2024)
======================================================================

📊 LISTENING STATS
   Total plays: 28,364
   Total listening time: 1,245.9 hours
   That's 51.9 days of music!
   Unique songs: 6,764
   Unique artists: 1,000
   Period: 2022-11-29 to 2024-11-17

🎵 TOP SONGS
   1. Eosophobia (229 plays)
   2. Psychosocial (177 plays)
   3. Hi-De-Ho (feat. Q-Tip) (176 plays)

🎤 TOP ARTISTS
   1. Jack White (2008 plays - 227.4h)
   2. Slipknot (1232 plays - 121.2h)
   3. Puscifer (871 plays - 96.0h)

🎸 TOP GENRES
   1. Alternative
   2. Rock
   3. Metal
======================================================================
```

---

## 📁 Project Structure

```
Music-Wrapped/
├── music_wrapped.py       # Main CLI entry point
├── apple_music_parser.py  # Apple Music data parser
├── analytics.py           # Unified analytics engine
├── wrapped_generator.py   # Image generation
├── artwork_fetcher.py     # Album/artist artwork from MusicBrainz
├── get_info.py           # Original Spotify integration
├── spotify_wrapped.py    # Original Spotify CLI
├── templates/            # Image templates
├── font/                 # Fonts for image generation
├── output/               # Generated images
└── requirements.txt      # Python dependencies
```

---

## 📋 Command Reference

```
usage: music_wrapped.py apple [-h] [--name NAME] [--year YEAR] [--all-years]
                               [--by-year] [--output OUTPUT] [--style STYLE]
                               [--artwork] [--exclude-artist ARTIST]
                               [--exclude-song SONG] [--exclude-genre GENRE]
                               data_dir

positional arguments:
  data_dir              Path to Apple Music Activity folder

options:
  -h, --help            Show help message
  -n, --name NAME       Name of the listener (for personalization)
  -y, --year YEAR       Filter to specific year
  --all-years           Analyze all years combined
  --by-year             Generate separate wrapped for each year
  -o, --output OUTPUT   Output directory for generated images
  -s, --style STYLE     Visual style: memorial, spotify_2021, spotify_2023, minimal
  -a, --artwork         Fetch album artwork from internet (slower)
  --exclude-artist      Exclude an artist (can use multiple times)
  --exclude-song        Exclude a song (can use multiple times)
  --exclude-genre       Exclude a genre (can use multiple times)
```

---

## 🔧 Requirements

- Python 3.8+
- pandas
- Pillow
- numpy
- requests
- musicbrainzngs (for artwork)
- spotipy (for Spotify API)

---

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Original [Spotify-Wrapped](https://github.com/hosseinmh1/Spotify-Wrapped) by Hossein Mohseni
- [MusicBrainz](https://musicbrainz.org/) for artist/album metadata
- [Cover Art Archive](https://coverartarchive.org/) for album artwork
