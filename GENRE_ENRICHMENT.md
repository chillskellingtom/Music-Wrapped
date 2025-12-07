# Genre Enrichment Guide

## Current Situation

Your Apple Music data has limited genre information:
- **Library Tracks**: Only 135 tracks have genres (out of thousands)
- **Daily Tracks**: 19,427 tracks, but Track Identifiers don't match Library Tracks
- **Result**: Only ~1% of songs have genres (73/6733)

## Solutions

### Option 1: Use Parser's Enriched Data (Current - Recommended First Step)

The `build_genre_lookup.py` script now uses the parser's enriched `daily_tracks`, which has Genre populated from library_tracks via Track Identifier matching.

**Run:**
```bash
python build_genre_lookup.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"
```

This should create more mappings than before, but still limited by what's in library_tracks.

### Option 2: External API Enrichment (Best for Maximum Coverage)

Use free APIs to look up genres for songs that don't have them.

#### A. Last.fm API (Free, No Auth Required)

**Get API Key:**
1. Go to https://www.last.fm/api
2. Create a free account
3. Create an application to get an API key

**Enrich existing genre_lookup.json:**
```bash
python enrich_genres_api.py \
  "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity/genre_lookup.json" \
  --lastfm-key YOUR_API_KEY \
  --max-lookups 5000
```

#### B. Spotify API (Free Tier Available)

**Get API Credentials:**
1. Go to https://developer.spotify.com/dashboard
2. Create an app
3. Get Client ID and Client Secret

**Enrich with Spotify:**
```bash
python enrich_genres_api.py \
  "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity/genre_lookup.json" \
  --spotify-client-id YOUR_CLIENT_ID \
  --spotify-client-secret YOUR_CLIENT_SECRET \
  --max-lookups 5000
```

**Note:** Spotify API has rate limits (1000 requests/hour for free tier). The script includes rate limiting.

#### C. Combined Approach (Best Results)

Use both APIs - Spotify first (more accurate), Last.fm as fallback:

```bash
python enrich_genres_api.py \
  "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity/genre_lookup.json" \
  --spotify-client-id YOUR_CLIENT_ID \
  --spotify-client-secret YOUR_CLIENT_SECRET \
  --lastfm-key YOUR_LASTFM_KEY \
  --max-lookups 5000
```

### Option 3: Other Files in Directory

Checked available files:
- ❌ `Music - Onboarding Genres.csv` - Not useful (empty/onboarding data)
- ❌ `Apple Music Library Albums.json` - No genre field
- ❌ `Apple Music Library Artists.json` - No genre field
- ✅ `Apple Music Library Tracks.json` - Already using (has genres for 135 tracks)

**Conclusion:** Other files don't have additional genre data.

## Recommended Workflow

1. **Build initial lookup** (uses parser's enriched data):
   ```bash
   python build_genre_lookup.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"
   ```

2. **Enrich with APIs** (for maximum coverage):
   ```bash
   python enrich_genres_api.py \
     "genre_lookup.json" \
     --lastfm-key YOUR_KEY \
     --max-lookups 5000
   ```

3. **Upload to Supabase**:
   ```bash
   python upload_data_to_supabase.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"
   ```

4. **Dashboard will automatically use it** - no code changes needed!

## Expected Results

- **Current**: ~1% genre coverage (73/6733 songs)
- **After parser enrichment**: ~5-10% (if parser matched more tracks)
- **After API enrichment**: 50-80%+ (depending on API success rate)

## API Rate Limits

- **Last.fm**: 5 requests/second (free tier)
- **Spotify**: 1000 requests/hour (free tier)

The scripts include rate limiting to respect these limits.

## Cost

- **Last.fm API**: Free
- **Spotify API**: Free tier available (1000 requests/hour)
- **Total Cost**: $0

