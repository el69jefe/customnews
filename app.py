import feedparser
import openai
import requests
import tempfile
import os
from flask import Flask, request, render_template, send_file
from pydub import AudioSegment

app = Flask(__name__)

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

def fetch_news_feed(url):
    return feedparser.parse(url)

def get_latest_articles(feed, num_articles=5):
    return feed.entries[:num_articles]

def summarize_articles(articles, openai_client, word_count):
    text = " ".join([article.summary for article in articles])
    prompt = f"Fasse den folgenden Text in etwa {word_count} Wörtern zusammen."
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    summary = response.choices[0].message.content.strip()
    return summary

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

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                fp.write(chunk)
        audio_file_path = fp.name

    print(f"Audio file saved at: {audio_file_path}")
    return audio_file_path

def add_background_music(voice_path, music_path):
    voice = AudioSegment.from_mp3(voice_path)
    background = AudioSegment.from_mp3(music_path)

    background_duration = len(voice) + 11000
    if len(background) > background_duration:
        background = background[:background_duration]

    initial_part = background[:6000]
    remaining_background = background[6000:]
    background_with_lower_volume = remaining_background - 20
    combined_background = initial_part + background_with_lower_volume
    combined = combined_background.overlay(voice, position=6000)
    voice_duration = len(voice)
    combined = combined[:6000 + voice_duration] + (combined[6000 + voice_duration:] + 20)
    final_segment = combined[:6000 + voice_duration + 5000]
    final_segment = final_segment.fade_out(2000)

    final_audio_path = tempfile.mktemp(suffix=".mp3")
    final_segment.export(final_audio_path, format="mp3")
    return final_audio_path

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        selected_categories = request.form.getlist('categories')
        total_time = int(request.form['total_time'])
        detail_level = int(request.form['detail_level'])
        background_music_path = "C:/Users/Niki/Desktop/CustomNews/Neuigkeiten.mp3"

        all_summaries = []
        openai_api_key = os.getenv("OPENAI_API_KEY")
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        openai_client = openai.OpenAI(api_key=openai_api_key)

        time_per_category = total_time / len(selected_categories)
        words_per_second = 2.5
        words_per_minute = words_per_second * 60
        words_per_article = detail_level * 5 * words_per_second
        words_per_category = time_per_category * words_per_minute
        articles_per_category = max(1, int(words_per_category / words_per_article))

        for category in selected_categories:
            feed_url = CATEGORIES[category]
            feed = fetch_news_feed(feed_url)
            articles = get_latest_articles(feed, articles_per_category)
            if not articles:
                continue
            summary = summarize_articles(articles, openai_client, int(words_per_category))
            all_summaries.append(f"{category}: \n{summary}")

        final_summary = "\n\n".join(all_summaries)
        audio_file_path = text_to_speech(final_summary, elevenlabs_api_key)
        final_audio_path = add_background_music(audio_file_path, background_music_path)

        return send_file(final_audio_path, as_attachment=True)

    return render_template('index.html', categories=CATEGORIES.keys())

if __name__ == "__main__":
    app.run(debug=True)
