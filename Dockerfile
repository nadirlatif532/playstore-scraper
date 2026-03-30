FROM python:3.9

# 1. Install Node.js
RUN curl -sL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

WORKDIR /code

# 2. Copy everything (Ensure .dockerignore exists to skip large folders!)
COPY . .

# 3. Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install google-play-scraper

# 4. Permissions for Hugging Face
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# 5. Start the engine
CMD ["gunicorn", "-b", "0.0.0.0:7860", "--timeout", "120", "app:app"]