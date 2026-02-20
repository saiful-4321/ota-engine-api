# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Make port 7000 available to the world outside this container
EXPOSE 7700

ENV PYTHONPATH=/app