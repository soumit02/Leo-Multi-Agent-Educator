import os
import time
import streamlit as st
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM

# Load environment variables
# Since this file is in src/streamlit/, the .env file is two levels up
load_dotenv('../../.env')

# --- Configuration Setup ---
st.set_page_config(page_title="Leo: Multi-Agent AI Tutor", page_icon="🤖", layout="wide")

# --- Session State Management ---
# Moved to the top so we can determine which LLM to load before initializing agents
if 'active_llm_tier' not in st.session_state:
    st.session_state.active_llm_tier = 'primary'
if 'phase' not in st.session_state:
    st.session_state.phase = 'input'
if 'lesson_content' not in st.session_state:
    st.session_state.lesson_content = ""
if 'quiz_content' not in st.session_state:
    st.session_state.quiz_content = ""
if 'topic' not in st.session_state:
    st.session_state.topic = ""
if 'reteach_count' not in st.session_state:
    st.session_state.reteach_count = 0

# --- Dynamic LLM Loader ---
@st.cache_resource(show_spinner=False)
def get_llm(tier):
    if tier == 'primary':
        token = os.getenv("GROQ_API_KEY")
        endpoint = os.getenv("BASE_URL")
        model_name = os.getenv("MODEL_NAME")
        
        if not token or not model_name:
            st.error("Primary API credentials missing in .env file.")
            st.stop()
            
        fixed_model_name = f"openai/{model_name}"
        return LLM(model=fixed_model_name, api_key=token, base_url=endpoint, temperature=0.5)
        
    elif tier == 'fallback':
        token = os.getenv("FALLBACK_API_KEY")
        endpoint = os.getenv("FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
        model_name = os.getenv("FALLBACK_MODEL_NAME", "openai/gpt-oss-20b")
        
        if not token or not model_name:
            st.error("Fallback API credentials missing in .env file.")
            st.stop()
            
        fixed_fallback_model = f"openai/{model_name}"
        return LLM(model=fixed_fallback_model, api_key=token, base_url=endpoint, temperature=0.5)

# Load the LLM based on the current active tier
llm = get_llm(st.session_state.active_llm_tier)

# --- Custom UI Function for Active Agent Indicator ---
def show_active_agents(phase):
    st.markdown("### 📡 Live Agent Status")
    
    col1, col2, col3, col4 = st.columns(4)
    
    states = {
        'coordinator': {'active': False, 'status': 'Idle', 'icon': '👨‍💼', 'name': 'Coordinator'},
        'explainer': {'active': False, 'status': 'Idle', 'icon': '👨‍🏫', 'name': 'Explainer'},
        'quiz_master': {'active': False, 'status': 'Idle', 'icon': '❓', 'name': 'Quiz Master'},
        'evaluator': {'active': False, 'status': 'Idle', 'icon': '🧑‍🏫', 'name': 'Evaluator'}
    }
    
    if phase == 'teaching':
        states['coordinator']['active'] = True
        states['coordinator']['status'] = 'Delegating...'
        states['explainer']['active'] = True
        states['explainer']['status'] = 'Writing Lesson...'
        states['quiz_master']['active'] = True
        states['quiz_master']['status'] = 'Creating Quiz...'
    elif phase == 'evaluating':
        states['evaluator']['active'] = True
        states['evaluator']['status'] = 'Grading Answers...'
        
    def render_agent_card(agent_info):
        border_color = "#00FF00" if agent_info['active'] else "#cccccc"
        bg_color = "rgba(0, 255, 0, 0.1)" if agent_info['active'] else "transparent"
        status_color = "green" if agent_info['active'] else "gray"
        
        card_html = f"""
        <div style="border: 2px solid {border_color}; border-radius: 10px; padding: 15px; text-align: center; background-color: {bg_color}; margin-bottom: 20px;">
            <div style="font-size: 2em; margin-bottom: 10px;">{agent_info['icon']}</div>
            <div style="font-weight: bold; font-size: 1.1em;">{agent_info['name']}</div>
            <div style="color: {status_color}; font-size: 0.9em; margin-top: 5px;">{agent_info['status']}</div>
        </div>
        """
        return card_html

    with col1:
        st.markdown(render_agent_card(states['coordinator']), unsafe_allow_html=True)
    with col2:
        st.markdown(render_agent_card(states['explainer']), unsafe_allow_html=True)
    with col3:
        st.markdown(render_agent_card(states['quiz_master']), unsafe_allow_html=True)
    with col4:
        st.markdown(render_agent_card(states['evaluator']), unsafe_allow_html=True)

# --- Agent Definitions ---
coordinator = Agent(
    role="Tutor Coordinator and Manager",
    goal="Manage the AI tutoring team, understand the student's request, and delegate teaching and quizzing tasks.",
    backstory="You are Leo, the master coordinator of an AI tutoring system. You oversee the Explainer, Quiz Master, and Evaluator.",
    allow_delegation=True, 
    verbose=False,
    llm=llm
)

explainer = Agent(
    role="Concept Explainer",
    goal="Explain the topic clearly and simply to the student.",
    backstory="You are a patient and highly knowledgeable teacher. You break down complex topics into easy-to-understand lessons.",
    allow_delegation=False,
    verbose=False,
    llm=llm
)

quiz_master = Agent(
    role="Quiz Master",
    goal="Create exactly 2 short Multiple Choice Questions (MCQs) based on the explanation.",
    backstory="You are an expert at assessing student knowledge. You generate exactly 2 short MCQs, each with 4 options (A, B, C, D).",
    allow_delegation=False,
    verbose=False,
    llm=llm
)

evaluator = Agent(
    role="Answer Evaluator",
    goal="Evaluate the student's selected MCQ options and provide a final verdict.",
    backstory=(
        "You are a strict but encouraging grader. "
        "You will receive the 2 MCQs and the student's provided answers. "
        "1. Identify the correct answers. "
        "2. Compare them with the student's answers. "
        "3. If BOTH are correct, congratulate them and explain why briefly. "
        "4. If ANY answer is incorrect, explain why and explicitly output 'RE-TEACH NEEDED'. "
        "Do NOT ask any further questions."
    ),
    allow_delegation=False,
    verbose=False,
    llm=llm 
)


# --- Main Application UI ---
st.title("🤖 Leo: Your AI Tutoring Team")
st.markdown("---")

# ==========================================
# Phase 1: Topic Input
# ==========================================
if st.session_state.phase == 'input':
    st.subheader("What do you want to learn today?")
    topic = st.text_input("Enter a topic:", placeholder="e.g., How does an API work?")
    
    if st.button("Start Learning", type="primary"):
        if topic.strip():
            st.session_state.topic = topic
            st.session_state.phase = 'teaching'
            st.rerun()
        else:
            st.warning("Please enter a topic to begin.")

# ==========================================
# Phase 2: Teaching & Quizzing (Crew 1)
# ==========================================
elif st.session_state.phase == 'teaching':
    st.header(f"📚 Topic: {st.session_state.topic}")
    
    show_active_agents('teaching')
    
    with st.spinner("Preparing your lesson and quiz... Please wait."):
        topic_context = st.session_state.topic
        
        if st.session_state.reteach_count > 0:
            topic_context += " (NOTE: The student provided incorrect answers to the previous quiz. Please explain the concept more simply, using different and easier real-world examples.)"

        explain_task = Task(
            description=f"Write a clear, engaging, and easy-to-understand lesson on this topic: {topic_context}",
            expected_output="A well-structured lesson on the topic with examples.",
            agent=explainer
        )

        quiz_task = Task(
            description="Based on the explanation, create exactly TWO short Multiple Choice Questions (MCQs) with options A, B, C, and D. Do NOT answer them in the output.",
            expected_output="Two short MCQ questions with 4 options each.",
            agent=quiz_master,
            context=[explain_task]
        )

        teaching_crew = Crew(
            agents=[explainer, quiz_master],
            tasks=[explain_task, quiz_task],
            manager_agent=coordinator,
            process=Process.hierarchical,
            memory=False,
            verbose=False
        )
        
        # Robust Mid-Flight Error Handling
        try:
            teaching_crew.kickoff(inputs={"topic": topic_context})
            
            # Save output to session state only if successful
            st.session_state.lesson_content = explain_task.output.raw
            st.session_state.quiz_content = quiz_task.output.raw
            st.session_state.phase = 'quizzing'
            st.rerun()
            
        except Exception as e:
            if st.session_state.active_llm_tier == 'primary':
                st.session_state.active_llm_tier = 'fallback'
               # st.warning("⚠️ Primary AI model reached its token limit mid-way. Automatically switching to Backup AI...")
                time.sleep(3) # Let the user read the warning
                st.rerun()
            else:
                st.error("🚨 The system is currently experiencing high demand (Too many requests). Please try again in a few minutes.")
                st.stop()

# ==========================================
# Phase 3: Display Lesson & Get Student Answer (Human-in-the-Loop)
# ==========================================
elif st.session_state.phase == 'quizzing':
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.header("📖 Your Lesson")
        st.write(st.session_state.lesson_content)
        
    with col2:
        st.header("📝 Quiz Time")
        st.info("Read the lesson on the left and answer the questions below.")
        st.write(st.session_state.quiz_content)
        
        st.markdown("### Your Answers")
        with st.form("quiz_form"):
            ans1 = st.text_input("Answer for Question 1 (e.g., A, B, C, or D):")
            ans2 = st.text_input("Answer for Question 2 (e.g., A, B, C, or D):")
            submitted = st.form_submit_button("Submit Answers", type="primary")
            
            if submitted:
                if ans1.strip() and ans2.strip():
                    st.session_state.student_ans = f"Question 1: {ans1.strip().upper()}, Question 2: {ans2.strip().upper()}"
                    st.session_state.phase = 'evaluating'
                    st.rerun()
                else:
                    st.warning("Please provide answers for both questions!")

# ==========================================
# Phase 4: Evaluation & Feedback Loop (Crew 2)
# ==========================================
elif st.session_state.phase == 'evaluating':
    st.header("⚖️ Evaluation")
    
    show_active_agents('evaluating')
    
    with st.spinner("Checking your answers against the correct facts..."):
        evaluate_task = Task(
            description=(
                f"The lesson was:\n{st.session_state.lesson_content}\n\n"
                f"The questions were:\n{st.session_state.quiz_content}\n\n"
                f"The student's answers are: {st.session_state.student_ans}\n\n"
                "1. Determine the correct answers based on the lesson.\n"
                "2. Compare them with the student's answers.\n"
                "3. If BOTH answers are correct, provide positive feedback.\n"
                "4. If ANY answer is incorrect, explain why and explicitly output 'RE-TEACH NEEDED'."
            ),
            expected_output="Final feedback stating if answers are Correct or Incorrect. Must include 'RE-TEACH NEEDED' if any answer is wrong.",
            agent=evaluator
        )

        eval_crew = Crew(
            agents=[evaluator],
            tasks=[evaluate_task],
            verbose=False
        )
        
        # Robust Mid-Flight Error Handling for Evaluation
        try:
            eval_result = eval_crew.kickoff()
            feedback_text = str(eval_result)
            
            st.markdown("### Feedback")
            st.write(feedback_text)
            
            # Feedback Loop Logic
            if "RE-TEACH NEEDED" in feedback_text.upper():
                st.error("🚨 Some answers were incorrect. The Tutor will re-teach the topic using easier examples.")
                st.session_state.reteach_count += 1
                if st.button("Start Re-learning", type="primary"):
                    st.session_state.phase = 'teaching'
                    st.rerun()
            else:
                st.success("🎉 Congratulations! You have perfectly mastered this topic.")
                if st.button("Learn a New Topic", type="primary"):
                    st.session_state.phase = 'input'
                    st.session_state.reteach_count = 0
                    st.lesson_content = ""
                    st.quiz_content = ""
                    st.rerun()
                    
        except Exception as e:
            if st.session_state.active_llm_tier == 'primary':
                st.session_state.active_llm_tier = 'fallback'
                st.warning("⚠️ Primary AI model reached its token limit mid-way. Automatically switching to Backup AI...")
                time.sleep(3)
                st.rerun()
            else:
                st.error("🚨 The system is currently experiencing high demand (Too many requests). Please try again in a few minutes.")
                st.stop()