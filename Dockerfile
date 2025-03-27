FROM python:3.12

# Install required dependencies, including Git
RUN apt update && apt install -y wget curl libc6 git

# Install Playwright and Flask dependencies
RUN pip install --no-cache-dir playwright flask flask-cors gunicorn

# Install Playwright browsers
RUN playwright install

# Set the working directory
WORKDIR /app

# Copy the application files
COPY . /app

# Expose the port for Railway
EXPOSE 8080

# Use Gunicorn as the start command
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "app:app"]
