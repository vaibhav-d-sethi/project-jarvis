"""Unit tests for strict quiz-response validation; uses only the stdlib."""
import unittest

from jarvis.quiz_parser import parse_quiz_output


class QuizParserTests(unittest.TestCase):
    def test_parses_json_array_and_normalizes_options(self):
        result = parse_quiz_output('''[
            {"question":"2+2?","options":{"A":"3","B":"4","C":"5","D":"6"},
             "correct_option":"B.","explanation":"Basic arithmetic."}
        ]''')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["options"], ["3", "4", "5", "6"])
        self.assertEqual(result[0]["correct_option"], "B")

    def test_parses_markdown_fenced_json(self):
        raw = '```json\n[{"question":"Q?","options":["a","b","c","d"],"correct_option":"A"}]\n```'
        self.assertEqual(parse_quiz_output(raw)[0]["correct_option"], "A")


    def test_accepts_lowercase_and_option_prefixed_keys(self):
        raw = """{"questions":[{"question":"Q?","options":{"option_a":"A) alpha","option_b":"B) beta","option_c":"C) gamma","option_d":"D) delta"},"correct_answer":"Option B"}]}"""
        result = parse_quiz_output(raw)[0]
        self.assertEqual(result["options"], ["alpha", "beta", "gamma", "delta"])
        self.assertEqual(result["correct_option"], "B")

    def test_accepts_option_objects_and_answer_text(self):
        raw = """[{"question":"Q?","choices":[{"text":"red"},{"label":"green"},{"value":"blue"},{"content":"gold"}],"answer":"BLUE"}]"""
        result = parse_quiz_output(raw)[0]
        self.assertEqual(result["correct_option"], "C")

    def test_accepts_json_with_surrounding_commentary(self):
        raw = 'Here is the quiz: [{"question":"Q?","options":["a","b","c","d"],"correct_option":"A"}] Hope this helps.'
        self.assertEqual(parse_quiz_output(raw)[0]["options"], ["a", "b", "c", "d"])

    def test_rejects_ambiguous_or_missing_correct_answer(self):
        raw = '[{"question":"Q?","options":["a","b","c","d"],"correct_option":"not sure"}]'
        with self.assertRaises(ValueError):
            parse_quiz_output(raw)

    def test_rejects_missing_options(self):
        with self.assertRaises(ValueError):
            parse_quiz_output('[{"question":"Q?","options":["a","b"],"correct_option":"A"}]')

    def test_rejects_non_json(self):
        with self.assertRaises(ValueError):
            parse_quiz_output('Here is your quiz!')


if __name__ == "__main__":
    unittest.main()
