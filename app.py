import feedparser
import openai
import requests
import tempfile
import os
from pydub import AudioSegment
from pydub.playback import play
from dotenv import load_dotenv

load_dotenv()

# Set the path to the ffmpeg binary
ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg', 'bin')
os.environ["PATH"] += os.pathsep + ffmpeg_path

# Define categories and their associated RSS feeds
CATEGORIES = {
    "Nachrichten": "https://taz.de/!p4608;rss/",
    "KI": "https://www.it-boltwise.de/themen/allgemein/feed",
    "Sport": "https://sportbild.bild.de/rss/vw-alle-artikel/vw-alle-artikel-45028184,sort=1,view=rss2.sport.xml",
    "Ukraine": "https://ukraine-nachrichten.de/index.php?rss=1",
    "Wunderwelt Wissen": "https://feeds.feedburner.com/scinexx",
    "Weltall": "https://www.spiegel.de/wissenschaft/weltall/index.rss",
    "Wallstreet": "https://www.wallstreet-online.de/rss/nachrichten-alle.xml"
}

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')


# Function to fetch news feed
def fetch_news_feed(url):
    return feedparser.parse(url)


# Function to get the latest articles from the feed
def get_latest_articles(feed, num_articles=5):
    return feed.entries[:num_articles]


# Function to summarize articles using OpenAI
def summarize_articles(articles, openai_client, word_count):
    text = " ".join([article.summary for article in articles])
    prompt = f"Fasse den folgenden Text in etwa {word_count} Wörtern zusammen."
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    summary = response.choices[0].message["content"].strip()
    return summary


# Function to convert text to speech using ElevenLabs API
def text_to_speech(text, elevenlabs_api_key):
    voice_id = "iMHt6G42evkXunaDU065"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": elevenlabs_api_key
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.2,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    # Save audio content to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                fp.write(chunk)
        audio_file_path = fp.name

    print(f"Audio file saved at: {audio_file_path}")
    return audio_file_path


# Function to add background music to the voice audio
def add_background_music(voice_path, music_path):
    voice = AudioSegment.from_mp3(voice_path)
    background = AudioSegment.from_mp3(music_path)

    # Truncate background music to match the duration of the voice audio + 11 seconds (5 seconds + 6 seconds)
    background_duration = len(voice) + 11000
    if len(background) > background_duration:
        background = background[:background_duration]

    # Initial part of background music (6 seconds) at normal volume
    initial_part = background[:6000]

    # Lower the volume of the background music by 10 dB after 6 seconds
    remaining_background = background[6000:]
    background_with_lower_volume = remaining_background - 20

    # Combine initial part and lower volume background
    combined_background = initial_part + background_with_lower_volume

    # Overlay voice on background music starting at 6 seconds
    combined = combined_background.overlay(voice, position=6000)

    # Increase the volume of the music after the voice finishes
    voice_duration = len(voice)
    combined = combined[:6000 + voice_duration] + (combined[6000 + voice_duration:] + 20)

    # Add 5 more seconds of normal volume music after the voice
    final_segment = combined[:6000 + voice_duration + 5000]

    # Fade out the background music for the last 2 seconds
    final_segment = final_segment.fade_out(2000)

    # Export the final audio to a temporary file
    final_audio_path = tempfile.mktemp(suffix=".mp3")
    final_segment.export(final_audio_path, format="mp3")
    return final_audio_path


# Main function
def main(openai_api_key, elevenlabs_api_key, background_music_path):
    print("Verfügbare Kategorien:")
    for i, category in enumerate(CATEGORIES.keys(), 1):
        print(f"{i}. {category}")

    selected_indices = input(
        "Geben Sie die Nummern der Kategorien ein, an denen Sie interessiert sind (durch Kommas getrennt): ").split(",")
    selected_categories = [list(CATEGORIES.keys())[int(index) - 1] for index in selected_indices]

    total_time = int(input("Wie lange soll die Ausgabe sein (in Minuten)? "))
    detail_level = int(input("Wie detailliert sollen die Informationen sein (1-5)? "))

    time_per_category = total_time / len(selected_categories)
    words_per_second = 2.5  # Approximation: 150 words per minute / 60 seconds
    words_per_minute = words_per_second * 60
    words_per_article = detail_level * 5 * words_per_second
    words_per_category = time_per_category * words_per_minute
    articles_per_category = max(1, int(words_per_category / words_per_article))

    print(f"Berechne Artikel pro Kategorie: {articles_per_category} pro Kategorie")

    all_summaries = []
    openai_client = openai.OpenAI(api_key=openai_api_key)
    for category in selected_categories:
        feed_url = CATEGORIES[category]
        feed = fetch_news_feed(feed_url)
        articles = get_latest_articles(feed, articles_per_category)
        if not articles:
            print(f"Keine Artikel gefunden für die Kategorie '{category}'.")
            continue

        summary = summarize_articles(articles, openai_client, int(words_per_category))
        all_summaries.append(f"{category}: \n{summary}")

    final_summary = "\n\n".join(all_summaries)
    print("Zusammenfassung der Nachrichten:")
    print(final_summary)

    audio_file_path = text_to_speech(final_summary, elevenlabs_api_key)
    if audio_file_path:
        print(f"Audio wird abgespielt von: {audio_file_path}")
        final_audio_path = add_background_music(audio_file_path, background_music_path)
        audio = AudioSegment.from_mp3(final_audio_path)
        play(audio)
        # Clean up the temporary audio files
        os.remove(audio_file_path)
        os.remove(final_audio_path)
        print("Audio Datei abgespielt und entfernt.")
    else:
        print("Fehler beim Generieren des Audios")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()  # take environment variables from .env.

    # Get the environment variables for the API keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

    # Path to the background music file
    BACKGROUND_MUSIC_PATH = "C:/Users/Niki/Desktop/CustomNews/Neuigkeiten.mp3"

    main(OPENAI_API_KEY, ELEVENLABS_API_KEY, BACKGROUND_MUSIC_PATH)
