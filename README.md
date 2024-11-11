# kAIusbot

This project is a Streamlit web application that allows users to generate images based on text input, using LLama for text understanding and Stable Diffusion for image generation. 

The app also leverages Retrieval-Augmented Generation (RAG) to enhance the text model’s understanding by incorporating additional relevant context.

Features
- Text Understanding: process and understand user input text with LLama, a powerful large language model.
- Image Generation: create somewhat understandable images with Stable Diffusion based on the processed text.
- Retrieval-Augmented Generation (RAG): improve responses by retrieving relevant information and augmenting the input text.
- Streamlit UI: simple, interactive web interface.
- Dockerized: easily set up and run the application in a containerized environment.

## Demo

(Include a screenshot of the app interface here or link to a hosted version if available)

## Setup
### Prerequisites

- Docker: make sure you have Docker installed.
- Python 3.12+: (Optional) if running locally without Docker.
- Pdm: (Optional) dependency management.
- expand o this later

### Running with Docker

Clone the Repository:
```bash
$ git clone https://github.com/kaiusdepaula/kAIusbot.git
$ cd kAIusbot
```

Build `docker` image:
```bash
$ docker build -t ai-image-generator .
```

Run the container:
```bash
docker run -p 8501:8501 ai-image-generator
```

Acess the app (locally):
```
http://localhost:8501
```


## Running without docker

Install dependencies using arch. You will need `pipx` here. You can install it [here](https://github.com/pypa/pipx):
```bash
$ pipx install .
```

Run the app:
```bash
$ streamlit run app.py
```

## Usage

Just like using chatbots, talk to it on the input space. Whenever it identifies you wish to generate an image, it'll automatically generate a prompt to StableDiffusion and run in on CPU. *Note that it'll be very slow.* 

If you wish to run it locally using GPU, I'll try to set something up for AMD. NVidia will probably work out of the box. On the webapp it'll never run on gpu as I'm not planning to spend a lot of money here.


## Configuration

Customize settings for the models in the config.yaml file:

LLama Model Settings: choose the version and parameters for text understanding.

Stable Diffusion Settings: adjust the model version and sampling steps.

RAG Settings: set up retrieval options, such as database location or API endpoint.


That's all folks!