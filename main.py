import json
import os
import requests
from dropbox import Dropbox
from dropbox.exceptions import ApiError
from dropbox.files import WriteMode
import schedule
import time
from datetime import datetime

# ENV variables
DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")
USERNAME = '1339565397'
dbx = Dropbox(DROPBOX_TOKEN)


def job():
    print(f"\n--- Running at {datetime.now().strftime('%H:%M:%S')} ---")
    main()


# Helpers to manage JSON files
def load_ids(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_ids(filename, ids):
    with open(filename, 'w') as f:
        json.dump(list(ids), f)


# SoundCloud
def get_liked_tracks():
    url = f"https://api-v2.soundcloud.com/users/{USERNAME}/likes?client_id={SOUNDCLOUD_CLIENT_ID}&limit=1"
    headers = {
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        return [
            item['track'] for item in data['collection'] if 'track' in item
        ]
    else:
        print(
            f"Failed to fetch liked tracks. Status: {response.status_code}, Response: {response.text}"
        )
        return []


def download_and_upload(track):
    title = track['title'].replace('/', '_') + '.mp3'
    transcodings = track.get('media', {}).get('transcodings', [])

    # 🎯 Chercher un flux MP3 progressif (le seul qui fonctionne offline)
    mp3_stream = next(
        (t for t in transcodings if t['format']['protocol'] == 'progressive'),
        None)

    if not mp3_stream:
        print(f"Aucun flux MP3 progressif disponible pour {title}")
        return False

    # ✅ Obtenir l'URL de téléchargement
    stream_info_url = f"{mp3_stream['url']}?client_id={SOUNDCLOUD_CLIENT_ID}"
    stream_response = requests.get(stream_info_url)
    if stream_response.status_code != 200:
        print(f"Erreur lors de la récupération du flux pour {title}")
        return False

    download_url = stream_response.json().get('url')
    if not download_url:
        print(f"URL de téléchargement introuvable pour {title}")
        return False

    print(f"Téléchargement de {title} depuis {download_url}")
    audio_response = requests.get(download_url)
    if audio_response.status_code != 200:
        print(f"Échec du téléchargement audio pour {title}")
        return False

    try:
        # 💾 Sauvegarder localement
        with open(title, 'wb') as f:
            f.write(audio_response.content)

        # ☁️ Upload vers Dropbox
        print(f"Upload vers Dropbox : {title}")
        with open(title, 'rb') as f:
            try:
                dbx.files_upload(f.read(),
                                 f"/SoundCloudDownloads/{title}",
                                 mode=WriteMode.add,
                                 mute=True)
            except ApiError as e:
                if e.error.is_path() and e.error.get_path().is_conflict():
                    print(f"{title} existe déjà sur Dropbox. Upload ignoré.")
                    return True
                else:
                    print(f"Erreur upload Dropbox pour {title}: {e}")
                    return False

        return True
    except Exception as e:
        print(f"Erreur générale pour {title} : {e}")
        return False
    finally:
        if os.path.exists(title):
            os.remove(title)


# Main
def main():
    downloaded_ids = load_ids("downloaded_tracks.json")
    failed_ids = load_ids("failed_tracks.json")

    liked_tracks = get_liked_tracks()

    new_tracks = [
        track for track in liked_tracks
        if track['id'] not in downloaded_ids and track['id'] not in failed_ids
    ]

    if not new_tracks:
        print("No new liked tracks to process.")
        return

    for track in new_tracks:
        success = download_and_upload(track)
        if success:
            downloaded_ids.add(track['id'])
        else:
            failed_ids.add(track['id'])

    save_ids("downloaded_tracks.json", downloaded_ids)
    save_ids("failed_tracks.json", failed_ids)


if __name__ == "__main__":
    main()

