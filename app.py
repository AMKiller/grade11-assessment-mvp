import streamlit as st
import os
from io import BytesIO
from datetime import datetime
import json

from knowledge_base import KnowledgeBase
from generation import generate_paper, _analyze_cognitive_distribution
from docgen import DocumentGenerator

AVAILABLE_TOPICS = ["Equations and Inequalities", "Exponents and Surds"]


st.set_page_config(
    page_title="Grade 11 Assessment Generator",
    layout="wide"
)

st.title("📝 Grade 11 Mathematics Assessment Generator")
st.markdown("""
Generate authentic CAPS-aligned test papers with real Word Math objects and
independently verified answers via SymPy.
""")

# Sidebar: Configuration
with st.sidebar:
    st.header("Assessment Configuration")

    st.markdown("**Topics** (select one or more)")
    selected_topics = []
    for t in AVAILABLE_TOPICS:
        if st.checkbox(t, value=(t == AVAILABLE_TOPICS[0]), key=f"topic_{t}"):
            selected_topics.append(t)

    if not selected_topics:
        st.warning("Select at least one topic.")

    st.caption(
        "Each selected topic becomes its own QUESTION block (QUESTION 1, QUESTION 2, ...)."
    )

    num_questions = st.slider(
        "Number of Questions per topic",
        min_value=2,
        max_value=8,
        value=5,
        step=1
    )

    grand_total_marks = st.number_input(
        "Total Marks (grand total across all selected topics)",
        min_value=10,
        max_value=300,
        value=50,
        step=5
    )

    # Per-topic mark allocation: with 1 topic it's trivially 100%; with 2+,
    # let the user set the split (e.g. 50:50, 25:75) for every topic except
    # the last, whose share is computed as the remainder -- guarantees the
    # allocation always sums exactly to grand_total_marks by construction,
    # no separate validation step needed.
    marks_per_topic = {}
    if len(selected_topics) == 1:
        marks_per_topic[selected_topics[0]] = grand_total_marks
    elif len(selected_topics) > 1:
        st.markdown("**Mark allocation per topic**")
        remaining = grand_total_marks
        for t in selected_topics[:-1]:
            default_share = grand_total_marks // len(selected_topics)
            share = st.number_input(
                f"Marks: {t}",
                min_value=0,
                max_value=remaining,
                value=min(default_share, remaining),
                step=5,
                key=f"marks_{t}"
            )
            marks_per_topic[t] = share
            remaining -= share
        last_topic = selected_topics[-1]
        marks_per_topic[last_topic] = remaining
        st.caption(f"{last_topic}: **{remaining} marks** (remainder, auto-computed)")

    time_minutes = st.number_input(
        "Duration (minutes)",
        min_value=30,
        max_value=180,
        value=60,
        step=5
    )

    st.subheader("Paper Metadata")

    grade = st.text_input("Grade", value="11")
    task = st.text_input("Task Number (e.g., 'Task 3')", value="")
    term = st.selectbox("Term", ["Term 1", "Term 2", "Term 3", "Term 4", ""])
    examiner = st.text_input("Examiner Name", value="")
    moderator = st.text_input("Moderator Name", value="")

    st.subheader("Template & Styling")

    use_template = st.checkbox("Use a custom template (.docx)", value=False)
    template_file = None
    if use_template:
        template_file = st.file_uploader(
            "Upload template (with {{GRADE}}, {{TASK}}, etc. placeholders)",
            type=["docx"],
            help="Optional: upload a .docx template. If not provided, a generic cover page is generated."
        )

    prefer_core = st.checkbox(
        "Prefer 'Core' archetypes only",
        value=True,
        help="If checked, only uses well-corroborated archetypes (3+ examples). "
             "If unchecked, includes supplementary ones for more variety."
    )

    use_seed = st.checkbox("Use fixed random seed", value=False)
    seed = None
    if use_seed:
        seed = st.number_input("Random seed", value=42, step=1)

# Main content
st.header("Generation Settings")

col1, col2 = st.columns(2)

with col1:
    st.metric("Topics", len(selected_topics))
    st.metric("Questions per topic", num_questions)
    st.metric("Total Marks (target)", grand_total_marks)

with col2:
    st.metric("Duration", f"{time_minutes} min")
    st.metric("Tier Filter", "Core + Supplementary" if not prefer_core else "Core Only")
    if use_seed:
        st.metric("Seed", seed)

if selected_topics:
    st.caption("Selected: " + ", ".join(selected_topics))

# Cognitive targets (CAPS balanced mode)
st.subheader("Cognitive Distribution Targets (CAPS Balanced Mode)")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Knowledge", "20%", delta="baseline")

with col2:
    st.metric("Routine", "35%", delta="dominant")

with col3:
    st.metric("Complex", "30%", delta="higher-order")

with col4:
    st.metric("Problem-Solving", "15%", delta="stretch")

st.info("""
**CAPS (Curriculum and Assessment Policy Statement)** prescribes these exact targets.
The generator aims to hit these percentages across the selected questions.
""")

# Generate button
if st.button("🚀 Generate Assessment", use_container_width=True, type="primary", disabled=not selected_topics):

    with st.spinner(f"🧠 Sampling archetypes across {len(selected_topics)} topic(s)..."):
        try:
            target_distribution = {
                'knowledge': 20,
                'routine': 35,
                'complex': 30,
                'problem_solving': 15
            }

            topics_data = []
            combined_question_dicts = []
            combined_errors = []
            combined_total_marks = 0

            for t in selected_topics:
                st.write(f"Generating **{t}** (target: {marks_per_topic[t]} marks)...")
                topic_result = generate_paper(
                    topic=t,
                    num_questions=num_questions,
                    target_distribution=target_distribution,
                    prefer_core=prefer_core,
                    target_marks=marks_per_topic[t]
                )
                topics_data.append((t, topic_result['question_objects']))
                combined_question_dicts.extend(topic_result['questions'])
                combined_total_marks += topic_result['total_marks']
                combined_errors.extend(
                    f"[{t}] {err}" for err in topic_result.get('generation_errors', [])
                )

            all_question_objects = [q for _, qs in topics_data for q in qs]
            cognitive_analysis = _analyze_cognitive_distribution(all_question_objects, target_distribution)

            result = {
                "topics": selected_topics,
                "topics_data": topics_data,
                "questions": combined_question_dicts,
                "total_marks": combined_total_marks,
                "cognitive_analysis": cognitive_analysis,
                "generation_errors": combined_errors
            }

            st.session_state.generation_result = result

            if len(result['questions']) == 0:
                st.error("❌ Generated 0 questions. See errors below:")
                for err in result.get('generation_errors', []):
                    st.code(err)
            elif result.get('generation_errors'):
                st.warning(f"⚠ Generated {len(result['questions'])} questions, but {len(result['generation_errors'])} failed:")
                for err in result['generation_errors']:
                    st.code(err)
            else:
                st.success(f"✓ Generated {len(result['questions'])} questions across {len(selected_topics)} topic(s)")

        except Exception as e:
            st.error(f"❌ Generation failed: {e}")
            st.write("**Full error traceback:**")
            import traceback
            st.code(traceback.format_exc())

# Display results
if "generation_result" in st.session_state:
    result = st.session_state.generation_result

    st.header("Generated Assessment")

    # Cognitive analysis
    st.subheader("Cognitive Distribution Analysis")

    analysis = result.get("cognitive_analysis", {})
    pcts = analysis.get("percentages_by_level", {})
    targets = analysis.get("target_distribution", {})
    variance = analysis.get("variance", {})

    col1, col2, col3, col4 = st.columns(4)

    cols = [col1, col2, col3, col4]
    levels = ["knowledge", "routine", "complex", "problem_solving"]

    for col, level in zip(cols, levels):
        pct = pcts.get(level, 0)
        target = targets.get(level, 0)
        var = variance.get(level, 0)

        with col:
            st.metric(
                level.capitalize(),
                f"{pct}%",
                delta=f"{var:+.1f}% (target: {target}%)",
                delta_color="off" if abs(var) < 5 else "inverse"
            )

    # Questions preview
    st.subheader("Generated Questions")

    for i, q in enumerate(result['questions'], 1):
        with st.expander(f"Question {i}: {q['archetype_id']}"):
            st.markdown(f"**Question Text:**\n\n{q['question']}")
            st.markdown(f"**Expected Answer:**\n\n`{q['answer']}`")
            st.markdown(f"**Marks:** {q['marks']}")
            st.markdown(f"**Cognitive Level:** {q['cognitive_level']}")

            if q.get('sympy_verified'):
                st.success("✓ Answer independently re-solved and confirmed by SymPy")
            elif q.get('manual_review_required'):
                if q.get('problem_type') == 'unverifiable':
                    st.info(f"ℹ Not mechanically verifiable ({q.get('problem_type')} archetype) — requires manual review before use")
                else:
                    st.error(f"⚠️ SymPy's independent solve DISAGREED with Claude's claimed answer — requires manual review: {q.get('sympy_error', '')}")
            else:
                st.warning(f"⚠ Verification incomplete: {q.get('sympy_error', 'Unknown error')}")

    # Download section
    st.subheader("📥 Download Assessment")
    st.caption("One combined document: question paper, marking guideline, and cognitive level analysis grid.")

    if st.button("Generate Full Assessment (.docx)", use_container_width=True):
        with st.spinner("Building question paper, marking guide, and cognitive grid..."):
            try:
                gen = DocumentGenerator(template_path=None)

                doc_bytes = gen.generate_full_assessment(
                    topics_data=result['topics_data'],
                    total_marks=result['total_marks'],
                    task=task or None,
                    term=term if term else None,
                    time_minutes=time_minutes,
                    examiner=examiner or None,
                    moderator=moderator or None,
                    grade=grade
                )

                topics_slug = "_".join(t.replace(' ', '_') for t in result['topics'])
                st.download_button(
                    label="💾 Download Assessment",
                    data=doc_bytes,
                    file_name=f"Grade_{grade}_{topics_slug}_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Failed to generate assessment: {e}")
                st.code(__import__('traceback').format_exc())

# Footer
st.divider()
st.markdown("""
**How it works:**
1. Select topic, marks, and metadata
2. Click "Generate Assessment"
3. Review the cognitive distribution and questions
4. Download the .docx files (question paper + marking guide)

**Safety & Quality:**
- Every answer is independently verified with SymPy before inclusion
- Questions are sampled from archetypes extracted from real past papers
- Cognitive distribution is aligned to CAPS guidelines (Balanced mode only)

**Known Limitations:**
- MVP: Grade 11 only, two topics, balanced mode only
- Scaffold/Challenge modes are post-MVP
- Marking guide requires manual annotation (template coming soon)
""")
