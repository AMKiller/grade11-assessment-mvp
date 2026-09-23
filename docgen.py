import io
from pathlib import Path
from docx import Document
from table_helpers import (
    add_question_heading, add_question_table, add_question_total_row,
    add_grand_total_paragraph, add_marking_guide_question_table,
    set_document_page_setup, set_document_default_font,
    add_information_sheet_image
)


class DocumentGenerator:
    def __init__(self, template_path: str = None):
        """
        Args:
            template_path: Path to a .docx template with {{PLACEHOLDER}} tokens.
                          If None, create a generic cover page.
        """
        self.template_path = template_path
        self.info_sheet_path = Path(__file__).parent / "information_sheet_gr11_gr12.png"

    def generate_question_paper(self, questions: list, topic: str,
                               total_marks: int, task: str = None,
                               term: str = None, time_minutes: int = None,
                               examiner: str = None, moderator: str = None,
                               grade: str = "11") -> bytes:
        """
        Generate a question paper .docx.

        Args:
            questions: List of GeneratedQuestion objects
            topic: Topic name
            total_marks: Total marks on paper
            task, term, time_minutes, examiner, moderator: Metadata for cover page
            grade: Grade (default "11")

        Returns:
            .docx file as bytes
        """
        if self.template_path:
            doc = self._load_and_replace_template(
                topic, task, term, time_minutes, total_marks, examiner,
                moderator, grade
            )
        else:
            doc = Document()
            set_document_page_setup(doc)
            set_document_default_font(doc)
            self._add_generic_cover_page(doc, topic, task, term, time_minutes,
                                         total_marks, examiner, moderator, grade)

        self._add_questions_section(doc, questions, total_marks)

        return self._save_to_bytes(doc)

    def generate_marking_guide(self, questions: list, marking_data: dict,
                              topic: str, total_marks: int) -> bytes:
        """
        Generate a marking guide .docx.

        Args:
            questions: List of GeneratedQuestion objects
            marking_data: Dict mapping archetype_id -> marking steps
                         (from Claude or manual annotation)
            topic: Topic name
            total_marks: Total marks

        Returns:
            .docx file as bytes
        """
        doc = Document()
        set_document_page_setup(doc)
        set_document_default_font(doc)

        self._add_marking_guide_header(doc, topic)

        question_num = 1
        for question in questions:
            steps = marking_data.get(question.archetype_id, {}).get("steps", [])
            marks = question.marks

            step_groups = [{
                'num': f'{question_num}',
                'steps': [(step_to_parts(s), "✓") for s in steps],
                'marks': marks
            }]

            add_marking_guide_question_table(doc, question_num, step_groups)
            doc.add_paragraph()
            question_num += 1

        doc.add_paragraph()
        doc.add_grand_total_paragraph(total_marks)

        return self._save_to_bytes(doc)

    def _load_and_replace_template(self, topic: str, task: str, term: str,
                                   time_minutes: int, total_marks: int,
                                   examiner: str, moderator: str, grade: str):
        """Load a template and replace {{PLACEHOLDER}} tokens."""
        doc = Document(self.template_path)

        replacements = {
            "{{GRADE}}": grade,
            "{{TASK}}": task or "",
            "{{TERM}}": term or "",
            "{{TOTAL}}": str(total_marks),
            "{{TIME}}": f"{time_minutes} minutes" if time_minutes else "",
            "{{EXAMINER}}": examiner or "",
            "{{MODERATOR}}": moderator or "",
            "{{TOPIC}}": topic
        }

        for paragraph in doc.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    for run in paragraph.runs:
                        if key in run.text:
                            run.text = run.text.replace(key, value)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for key, value in replacements.items():
                            if key in paragraph.text:
                                for run in paragraph.runs:
                                    if key in run.text:
                                        run.text = run.text.replace(key, value)

        return doc

    def _add_generic_cover_page(self, doc, topic: str, task: str, term: str,
                                time_minutes: int, total_marks: int,
                                examiner: str, moderator: str, grade: str):
        """Build a simple cover page when no template is provided."""
        doc.add_heading(f"Grade {grade} Mathematics", level=1)
        doc.add_heading(topic, level=2)

        info_items = []
        if task:
            info_items.append(f"Task: {task}")
        if term:
            info_items.append(f"Term: {term}")
        if time_minutes:
            info_items.append(f"Time: {time_minutes} minutes")
        info_items.append(f"Total Marks: {total_marks}")
        if examiner:
            info_items.append(f"Examiner: {examiner}")
        if moderator:
            info_items.append(f"Moderator: {moderator}")

        for item in info_items:
            doc.add_paragraph(item)

        doc.add_page_break()

    def _add_questions_section(self, doc, questions: list, total_marks: int):
        """Add the questions and calculate spacing."""
        section_marks = 0
        for i, question in enumerate(questions, 1):
            q_row = {
                'num': str(i),
                'parts': [question.question_text],
                'marks': question.marks
            }
            add_question_table(doc, [q_row])
            section_marks += question.marks

        add_grand_total_paragraph(doc, total_marks)

    def _add_marking_guide_header(self, doc, topic: str):
        """Add header to marking guide."""
        doc.add_heading(f"Marking Guide: {topic}", level=1)
        doc.add_paragraph()

    def _save_to_bytes(self, doc) -> bytes:
        """Save document to bytes buffer."""
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()


def step_to_parts(step_dict: dict) -> list:
    """Convert a marking step dict to content parts for table_helpers."""
    if isinstance(step_dict, str):
        return [step_dict]

    step_text = step_dict.get("step", "")
    has_math = step_dict.get("has_math", False)

    if has_math:
        latex = step_dict.get("latex", "")
        return [step_text, ("math", latex)]
    return [step_text]
