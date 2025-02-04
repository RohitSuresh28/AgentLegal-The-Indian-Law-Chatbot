import streamlit as st
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFaceEndpoint
from langchain.vectorstores import Pinecone as LangchainPinecone
from langchain.chains import RetrievalQA
import os
from pinecone import Pinecone, ServerlessSpec
import time
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge import Rouge
from bert_score import score
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import random 
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import plotly.graph_objects as go

nltk.download('vader_lexicon')


if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "feedback_history" not in st.session_state:
    st.session_state["feedback_history"] = []

# Initialize risk factor state
if "risk_factor" not in st.session_state:
    st.session_state["risk_factor"] = None

# Streamlit page configuration with a wide layout
st.set_page_config(page_title="AgentLegal", layout="wide")

# MySQL connection details
MYSQL_USERNAME = "root"  # Replace with your MySQL username
MYSQL_PASSWORD = "MYSQLPASSWORD"  # Replace with your MySQL password
MYSQL_HOST = "localhost"  # Change if your MySQL server is hosted elsewhere
MYSQL_PORT = "3306"  # Default MySQL port
MYSQL_DB = "legal_assistant_feedback"

# Create the SQLAlchemy engine for MySQL
engine = create_engine(f"mysql+mysqldb://root:ranj123%40Data@localhost:3306/legal_assistant_feedback")

# Define the base class for ORM models
Base = declarative_base()

# Define Feedback model (ORM table)
class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    feedback = Column(Text)

# Create a session to interact with the database
Session = sessionmaker(bind=engine)
session = Session()

# Initialize dark mode state
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

# Dark mode toggle
dark_mode = st.sidebar.checkbox("🌓 Toggle Dark Mode", value=st.session_state["dark_mode"])
st.session_state["dark_mode"] = dark_mode

# Add custom CSS for background color and conversational layout
if dark_mode:
    st.markdown(
        """
        <style>
        /* Dark mode styles */
        .stApp {
            background-color: #1e1e1e;
            color: white;
        }
        input {
            border: 2px solid #055289;
            border-radius: 10px;
            padding: 10px;
            color: white;
            background-color: #333;
            font-family: 'Arial', sans-serif;
        }
        button {
            background-color: #055289;
            color: white;
            border: none;
            padding: 10px 20px;
            text-align: center;
            border-radius: 10px;
            font-family: 'Arial', sans-serif;
        }
        .sidebar .sidebar-content {
            padding: 20px;
            color: white;
        }
        h1, h2, h3 {
            color: #055289;
        }
        .chatbox {
            background-color: #2a2a2a;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(255, 255, 255, 0.1);
            font-family: 'Arial', sans-serif;
        }
        </style>
        """, unsafe_allow_html=True
    )
else:
    st.markdown(
        """
        <style>
        /* Light mode styles */
        .stApp {
            background-color: #f0f2f6;
            color: black;
        }
        input {
            border: 2px solid #055289;
            border-radius: 10px;
            padding: 10px;
            color: #333;
        }
        button {
            background-color: #055289;
            color: white;
            border: none;
            padding: 10px 20px;
            text-align: center;
            border-radius: 10px;
        }
        .sidebar .sidebar-content {
            padding: 20px;
            color: #333;
        }
        h1, h2, h3 {
            color: #055289;
        }
        .chatbox {
            background-color: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        </style>
        """, unsafe_allow_html=True
    )

# Sidebar content
st.sidebar.title("Legal Assistant Chatbot")
st.sidebar.write("Ask legal questions, and the chatbot will provide answers based on Indian legal knowledge.")


# AI Insights Dashboard in the sidebar
st.sidebar.header("📊 AI Insights Dashboard")


total_queries = 0
avg_response_time = 0.0
sentiment_label = "N/A"
compound_score = 0.0


if "chat_history" in st.session_state:
   total_queries = len(st.session_state["chat_history"]) // 2  # Each query has a response
   avg_response_time = round(random.uniform(1, 2), 2)  # Simulating average response time
   sentiment_analyzer = SentimentIntensityAnalyzer()


   # Sentiment analysis
   if "sentiments" not in st.session_state:
       st.session_state["sentiments"] = []


   # Analyze the sentiment of the user's messages
   for i, (speaker, msg) in enumerate(st.session_state["chat_history"]):
       if speaker == "You":  # Only analyze user queries
           sentiment_score = sentiment_analyzer.polarity_scores(msg)
           st.session_state["sentiments"].append(sentiment_score)


   # Display sentiment score for the last user message
   if st.session_state["sentiments"]:
       last_sentiment = st.session_state["sentiments"][-1]
       compound_score = last_sentiment['compound']


       # Determine if the sentiment is Positive, Negative, or Neutral
       if compound_score > 0:
           sentiment_label = "Positive"
       elif compound_score < 0:
           sentiment_label = "Negative"
       else:
           sentiment_label = "Neutral"


# Show some insights on the sidebar
st.sidebar.metric("Total Queries", total_queries)
st.sidebar.metric("Avg Response Time (s)", avg_response_time)
st.sidebar.subheader("Sentiment Analysis")
st.sidebar.write(f"Sentiment of last user message: {sentiment_label} (Score: {compound_score})")



# Main Title
st.title("AgentLegal")
st.write("Welcome to the Legal Assistant Agent! Ask questions about legal matters, contracts, compliance, and more.")

# Setup API tokens (hide API keys in real applications)
os.environ["HUGGINGFACEHUB_API_TOKEN"] = "HUGGING_FACE_API"
os.environ["PINECONE_API_KEY"] = "PINECONE_API"
os.environ["PINECONE_ENV"] = "PINECONE_ENV"

# Initialize Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = "document-embeddings"

# Create index if it doesn't exist
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=768,
        metric='cosine',
        spec=ServerlessSpec(cloud='aws', region=os.environ["PINECONE_ENV"])
    )

# Initialize the embedding model
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Initialize Langchain Pinecone Vector Store
vectorstore = LangchainPinecone.from_existing_index(index_name=index_name, embedding=embedding_model)

# Initialize the LLM
llm = HuggingFaceEndpoint(repo_id="mistralai/Mistral-Small-Instruct-2409")

# Initialize the RetrievalQA chain with embeddings and LLM
qa_chain = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=vectorstore.as_retriever())

# Chat history list
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []


# Layout for chatbot and dashboard
col1, col2 = st.columns([3, 1])

# Chatbot section (Left side)
with col1:
    # User query input
    user_query = st.text_input("Enter your legal question:")

    # Process the query when entered
    if user_query:
        instruction = ("You are a highly knowledgeable legal assistant. You have a good knowledge of indian legal system and corporate law. Your primary role is to assist users by answering their questions related to legal matters, contracts, compliance, and court cases.Provide accurate and concise answers based on your understanding of legal concepts and practices.If the input is a general greeting or unrelated to legal matters, politely acknowledge it without providing legal information. However, for all other queries related to legal matters, strive to provide a comprehensive answer based on your understanding. Always make sure your sentences are completed.")
        query_with_instruction = instruction + " " + user_query

        # Display a spinner while processing
        with st.spinner('Processing your query...'):
            start_time = time.time()
            response = qa_chain.run(query=query_with_instruction, max_length=500, return_only_outputs=True)
            end_time = time.time()
            response_time = end_time - start_time

        # Extract the helpful answer
        if isinstance(response, str):
            helpful_answer = response.split("Helpful Answer:")[-1].strip()
        else:
            helpful_answer = response.get("output", "No helpful answer found").strip()

        # Append the conversation to chat history
        st.session_state["chat_history"].append(("You", user_query))
        st.session_state["chat_history"].append(("AgentLegal", helpful_answer))

        # Feedback section
        feedback = st.radio("Was this answer helpful?", ("✅ Yes", "❌ No"), key="feedback")

        # Button to submit feedback
        if st.button("Submit Feedback"):
            if "feedback_history" not in st.session_state:
                st.session_state["feedback_history"] = []
        
        # Store feedback in session state
        st.session_state["feedback_history"].append({
            "query": user_query,
            "response": helpful_answer,
            "feedback": feedback
        })

        # Insert feedback into the MySQL database
        feedback_entry = Feedback(query=user_query, response=helpful_answer, feedback=feedback)
        session.add(feedback_entry)
        session.commit()

        st.success("Thank you for your feedback!")


# Display chat history in the main area
for speaker, msg in st.session_state["chat_history"]:
    st.markdown(f"<div class='chatbox'><strong>{speaker}:</strong> {msg}</div>", unsafe_allow_html=True)

with col2:
    st.header("Risk Factor")
    with col2:
    # Input box for user to enter a new risk factor
        risk_factor = st.number_input("Enter Risk Factor:", min_value=0, max_value=100, value=st.session_state["risk_factor"])

    # Update Risk Factor button
        if st.button("Update Risk"):
            st.session_state["risk_factor"] = risk_factor
            st.success(f"Risk Factor updated to {risk_factor}!")

    # Show the current risk factor
        st.subheader("Current Risk Factor")
        st.markdown(f"<h3 style='color: #dc3545;'>{st.session_state['risk_factor']}</h3>", unsafe_allow_html=True)
    
    # Display risk factor value
    st.write(f"Calculated Risk Factor: *{st.session_state['risk_factor']}*")

# Function to analyze feedback
def analyze_feedback():
    if "feedback_history" in st.session_state:
        total_feedback = len(st.session_state["feedback_history"])
        positive_feedback = sum(1 for fb in st.session_state["feedback_history"] if fb["feedback"] == "✅ Yes")
        negative_feedback = total_feedback - positive_feedback

        st.sidebar.subheader("Feedback Summary")
        st.sidebar.write(f"Total Feedback: {total_feedback}")
        st.sidebar.write(f"Positive Feedback: {positive_feedback}")
        st.sidebar.write(f"Negative Feedback: {negative_feedback}")

# Call the feedback analysis function
analyze_feedback()
