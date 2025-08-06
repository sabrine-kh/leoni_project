# LEOPARTS 🦁

A comprehensive Streamlit application for document processing, part extraction, and intelligent chatbot interactions using AI-powered tools.

## 🚀 Features

- **🤖 AI Chatbot**: Interactive chat interface powered by Groq and LangChain
- **📄 Document Processing**: PDF upload and processing with Mistral Vision API
- **🔍 Part Extraction**: Automated extraction of part attributes from documents
- **📊 Vector Search**: Advanced document search and retrieval capabilities
- **🎨 Modern UI**: Beautiful blue-themed interface with responsive design

## 🛠️ Tech Stack

- **Frontend**: Streamlit
- **AI/ML**: LangChain, Groq, Mistral AI, Sentence Transformers
- **Vector Database**: ChromaDB
- **Document Processing**: PyMuPDF, Playwright
- **Database**: Supabase
- **Async Handling**: Nest Asyncio

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd loeni_project
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file with your API keys:
   ```
   GROQ_API_KEY=your_groq_api_key
   MISTRAL_API_KEY=your_mistral_api_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   ```

## 🚀 Usage

1. **Run the application**
   ```bash
   streamlit run app.py
   ```

2. **Navigate through the app**:
   - **🏠 Home**: Main dashboard
   - **🤖 Chat with Leoparts**: AI-powered chatbot
   - **📄 Extract a new Part**: Document processing and attribute extraction
   - **🔍 Debug Interface**: Development and debugging tools

## 📁 Project Structure

```
loeni_project/
├── app.py                          # Main Streamlit application
├── pages/                          # Streamlit pages
│   ├── chatbot.py                  # AI chatbot interface
│   ├── extraction_attributs.py     # Document processing
│   └── evaluate_doc_search.py      # Search evaluation
├── utils/                          # Utility functions
├── requirements.txt                # Python dependencies
├── config.py                       # Configuration settings
├── vector_store.py                 # Vector database operations
├── pdf_processor.py                # PDF processing logic
└── llm_interface.py               # LLM integration
```

## 🔧 Configuration

The application uses several configuration files:
- `config.py`: Main configuration settings
- `numind_schema_config.py`: NuMind schema configuration
- `attribute_dictionary.json`: Attribute definitions

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For support and questions, please open an issue in the repository. 