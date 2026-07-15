#!/bin/bash

# Install Ollama (>= 0.5.0 required for llama.cpp grammar-constrained decoding)
curl -fsSL https://ollama.com/install.sh | sh

# Pull default model (llama3.1 supports tool calling; plain llama3:8b does not)
ollama pull gpt-oss:20b

# Install Python dependencies
uv sync