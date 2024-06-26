import feedparser
import openai
import requests
import tempfile
import os
from flask import Flask, request, render_template, send_file
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

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
    response = openai_client.chat_completions.create(
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


@app.route('/', methods=['GET', 'POST'])
def main():
    if request.method == 'POST':
        selected_categories = request.form.getlist('categories')
        total_time = int(request.form['total_time'])
        detail_level = int(request.form['detail_level'])

        time_per_category = total_time / len(selected_categories)
        words_per_second = 2.5  # Approximation: 150 words per minute / 60 seconds
        words_per_minute = words_per_second * 60
        words_per_article = detail_level * 5 * words_per_second
        words_per_category = time_per_category * words_per_minute
        articles_per_category = max(1, int(words_per_category / words_per_article))

        print(f"Berechne Artikel pro Kategorie: {articles_per_category} pro Kategorie")

        all_summaries = []
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
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

        audio_file_path = text_to_speech(final_summary, ELEVENLABS_API_KEY)
        if audio_file_path:
            print(f"Audio wird abgespielt von: {audio_file_path}")
            return send_file(audio_file_path, as_attachment=True)
        else:
            print("Fehler beim Generieren des Audios")
            return "Fehler beim Generieren des Audios", 500

    return render_template('index.html', categories=CATEGORIES)


if __name__ == "__main__":
    app.run(debug=True)
