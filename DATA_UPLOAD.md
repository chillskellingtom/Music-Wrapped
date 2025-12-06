# Uploading Apple Music Data to Supabase Storage

This guide shows you how to securely upload the Apple Music data to Supabase Storage so it's automatically available when users log into the dashboard.

---

## Step 1: Create Storage Bucket in Supabase

1. Go to: **https://supabase.com/dashboard/project/cgmiuzcjowdtaawtdmrg/storage/buckets**

2. Click **"New bucket"**

3. Fill in:
   - **Name:** `apple-music-data`
   - **Public bucket:** ❌ **OFF** (keep it private)
   - **File size limit:** 100 MB (or higher if needed)

4. Click **"Create bucket"**

---

## Step 2: Set Up Row Level Security (RLS)

1. Go to: **Storage** → **Policies** → **apple-music-data**

2. Click **"New Policy"**

3. Select **"For full customization"**

4. Name: `Allow authenticated users to read`

5. Policy definition:
   ```sql
   (bucket_id = 'apple-music-data'::text) AND (auth.role() = 'authenticated'::text)
   ```

6. Allowed operation: **SELECT** (read only)

7. Click **"Review"** → **"Save policy"**

This ensures only logged-in users can access the data.

---

## Step 3: Upload the Data

### Option A: Manual Upload via Dashboard (Easiest & Most Secure) ⭐ RECOMMENDED

1. Go to: **https://supabase.com/dashboard/project/cgmiuzcjowdtaawtdmrg/storage/buckets/apple-music-data**

2. Click **"Upload file"**

3. **For the large file (70MB):**
   - First, compress it locally:
     ```bash
     cd "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"
     gzip -9 "Apple Music Play Activity.csv"
     ```
   - Upload: `Apple Music Play Activity.csv.gz` (will be ~7.7MB)

4. **Upload the other essential files:**
   - `Apple Music - Play History Daily Tracks.csv`
   - `Apple Music - Track Play History.csv`
   - `Apple Music Library Tracks.json`
   - `Apple Music Library Artists.json`
   - `Apple Music - Top Content.csv`

5. **Done!** The dashboard will automatically decompress `.gz` files.

---

### Option B: Using the Upload Script (Requires Service Key)

**First, get your Service Role Key:**

1. Go to: **https://supabase.com/dashboard/project/cgmiuzcjowdtaawtdmrg/settings/api**
2. Scroll to **"Project API keys"**
3. Find **"service_role"** key (⚠️ **SECRET** - never expose this!)
4. Copy it

**Then run the upload:**

```bash
cd "/Users/pathayes/Library/Mobile Documents/com~apple~CloudDocs/development/github/repo-clones/Music-Wrapped"

# Set your Supabase credentials (use SERVICE_ROLE key for uploads)
export SUPABASE_URL="https://cgmiuzcjowdtaawtdmrg.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key-here"  # Get from Supabase Dashboard

# Run the upload script
python upload_data_to_supabase.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"
```

**Note:** The script automatically compresses large files (>10MB) to fit under the 50MB limit.

### Option B: Manual Upload via Supabase Dashboard

1. Go to: **Storage** → **apple-music-data**

2. Click **"Upload file"**

3. Upload each CSV and JSON file from the Apple Music Activity folder

4. Maintain the folder structure (create folders as needed)

---

## Step 4: Verify Upload

1. Go to: **Storage** → **apple-music-data**

2. You should see files like:
   - `Apple Music Play Activity.csv`
   - `Apple Music Library Tracks.json`
   - `Apple Music - Track Play History.csv`
   - etc.

---

## Step 5: Test the Dashboard

1. Go to: **https://pad-music-wrapped-app-a3ggwfytfjpykeefuxrt4k.streamlit.app**

2. Log in with your credentials

3. The dashboard should automatically load data from Supabase Storage

4. You should see: **"✅ Data loaded from secure storage"** in the sidebar

---

## Security Notes

- ✅ Data is stored in a **private bucket** (not publicly accessible)
- ✅ Only **authenticated users** can access it (via RLS policy)
- ✅ Data is **encrypted at rest** (Supabase handles this)
- ✅ Data is **encrypted in transit** (HTTPS)

---

## Troubleshooting

**"Could not access Supabase Storage"**
- Check that the bucket exists and is named `apple-music-data`
- Verify RLS policies are set correctly
- Make sure you're logged in

**"No data found"**
- Verify files were uploaded successfully
- Check file names match what the parser expects
- Look at browser console for errors

**Upload fails**
- Check file sizes (should be < 100MB per file)
- Verify Supabase credentials are correct
- Check your internet connection

