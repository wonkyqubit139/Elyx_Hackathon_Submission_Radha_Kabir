import streamlit as st
import google.generativeai as genai
import pandas as pd

# --- Configuration ---
API_KEY = "AIzaSyAwsTkCsRrUD1UX8PVMQZiiWYr89tbjSKA"

# --- Function to Generate Conversation ---
def generate_health_conversation():
    """
    Generates a simulated 8-month health conversation using an LLM.
    """
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

        prompt = """
        You are an advanced AI agent designed to simulate a comprehensive, 
        8-month-long conversation between a demanding health client named Rohan 
        and an AI health team (Ruby, Advik, Carla, Dr. Warren).

        Format output as:

        ## Conversation
        (800 messages across 8 months, structured with timestamps + names)

        ## Timeline Summary
        A structured monthly/episode timeline with goals, friction points, outcomes.

        ## Decisions & Why
        For each intervention (test/medication/therapy), give 2-3 sentences explaining
        why it was recommended, citing the relevant chat messages.

        ## Internal Metrics
        Table with: Response Time, Resolution Time, Hours by Doctors, Hours by Coach.

        ## Persona Analysis
        Before/After states of member’s mindset at major episodes.
        """

        response = model.generate_content(prompt)
        return response.text if hasattr(response, "text") else str(response)

    except Exception as e:
        print(f"❌ An error occurred: {e}")

# --- Streamlit UI ---
def main():
    st.title("🩺 Elyx Health Journey Simulator")

    st.markdown("This app simulates an **8-month health journey** for Rohan with the Elyx health team.")
    st.markdown("It shows not only the **conversation**, but also **timeline, decisions, metrics, and persona analysis**.")

    if st.button("Generate Journey"):
        with st.spinner("Generating conversation and analysis... please wait ⏳"):
            journey_text = generate_health_conversation()

        st.success("✅ Journey generated!")

        # Split sections
        sections = journey_text.split("## ")
        for sec in sections:
            if not sec.strip():
                continue
            if sec.startswith("Conversation"):
                st.subheader("💬 Conversation")
                st.markdown(sec.replace("Conversation", ""), unsafe_allow_html=True)

            elif sec.startswith("Timeline Summary"):
                st.subheader("📅 Timeline Summary")
                st.markdown(sec.replace("Timeline Summary", ""), unsafe_allow_html=True)

            elif sec.startswith("Decisions & Why"):
                st.subheader("🤔 Decisions & Why")
                st.markdown(sec.replace("Decisions & Why", ""), unsafe_allow_html=True)

            elif sec.startswith("Internal Metrics"):
                st.subheader("📊 Internal Metrics")
                # convert metrics to a dataframe
                lines = sec.splitlines()[1:]
                data = [l.split(":", 1) for l in lines if ":" in l]
                df = pd.DataFrame(data, columns=["Metric", "Value"])
                st.table(df)

            elif sec.startswith("Persona Analysis"):
                st.subheader("🧑 Persona Analysis")
                st.markdown(sec.replace("Persona Analysis", ""), unsafe_allow_html=True)


# --- Main execution block ---
if __name__ == "__main__":
    main()
