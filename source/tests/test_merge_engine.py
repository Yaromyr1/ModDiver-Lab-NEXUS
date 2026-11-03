import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from merge_engine import (
    MergeSafetyError, atomic_write, diff_runs, plan_merge, plan_merge_with_runs,
    validate_sealed_input, apply_file_transaction, recover_file_transaction,
)


class DiffRunsTests(unittest.TestCase):
    def test_no_changes(self):
        self.assertEqual(diff_runs(b"abc", b"abc"), [])

    def test_contiguous_ranges(self):
        self.assertEqual(
            [(r.start, r.end) for r in diff_runs(b"abcdefgh", b"aXXdefYh")],
            [(1, 2), (6, 6)],
        )

    def test_different_lengths_are_unsafe(self):
        self.assertIsNone(diff_runs(b"abc", b"abcd"))


class MergeTests(unittest.TestCase):
    def test_non_overlapping_edits_merge(self):
        merged, conflicts = plan_merge(
            b"abcdefgh",
            [("A", b"aBcdefgh"), ("B", b"abcdefgH")],
        )
        self.assertEqual(merged, b"aBcdefgH")
        self.assertEqual(conflicts, [])

    def test_overlapping_edits_report_and_later_wins(self):
        merged, conflicts = plan_merge(
            b"abcd",
            [("A", b"aXcd"), ("B", b"aYcd")],
        )
        self.assertEqual(merged, b"aYcd")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual((conflicts[0].start, conflicts[0].end), (1, 1))
        self.assertEqual((conflicts[0].earlier_mod, conflicts[0].later_mod), ("A", "B"))

    def test_same_value_write_is_not_conflict(self):
        merged, conflicts = plan_merge(
            b"abcd",
            [("A", b"aXcd"), ("B", b"aXcd")],
        )
        self.assertEqual(merged, b"aXcd")
        # Both mods change the same byte to the same value: no real conflict.
        self.assertEqual(len(conflicts), 0)

    def test_three_mods_track_latest_owner_after_partial_overlap(self):
        merged, conflicts = plan_merge(
            b"abcdefgh",
            [("A", b"aXXdefgh"), ("B", b"abcYefgh"), ("C", b"abZZefgh")],
        )
        self.assertEqual(merged, b"aXZZefgh")
        # C overlaps A at byte 2 and B at byte 3; ownership stays interval-based.
        self.assertTrue(any(c.earlier_mod == "A" and c.later_mod == "C" for c in conflicts))
        self.assertTrue(any(c.earlier_mod == "B" and c.later_mod == "C" for c in conflicts))

    def test_length_change_fails_closed(self):
        with self.assertRaises(MergeSafetyError):
            plan_merge(b"abc", [("A", b"abcd")])

    def test_empty_mod_list(self):
        merged, conflicts = plan_merge(b"abc", [])
        self.assertEqual(merged, b"abc")
        self.assertEqual(conflicts, [])

    def test_row_conflict_detected_when_later_mod_leaves_earlier_field_at_stock(self):
        stock = b"abcdefgh"
        earlier = b"Xbcdefgh"
        later = b"aYcdefgh"
        merged, conflicts = plan_merge(stock, [("A", earlier), ("B", later)], row_size=4)
        self.assertEqual(merged, b"XYcdefgh")
        self.assertEqual([(c.start, c.end, c.earlier_mod, c.later_mod) for c in conflicts],
                         [(0, 3, "A", "B")])

    def test_disjoint_byte_edits_in_same_row_report_one_row_conflict(self):
        stock = b"abcdefgh"
        earlier = b"aXcdefgh"
        later = b"aYcdefgh"
        _, conflicts = plan_merge(stock, [("A", earlier), ("B", later)], row_size=4)
        self.assertEqual([(c.start, c.end) for c in conflicts], [(0, 3)])

    def test_run_aware_planner_diffs_each_candidate_once(self):
        stock = b"abcdefgh"
        mods = [("A", b"aXcdefgh"), ("B", b"abcdefgY")]
        from merge_engine import diff_runs as real_diff_runs
        with patch("merge_engine.diff_runs", wraps=real_diff_runs) as diff:
            merged, conflicts, runs = plan_merge_with_runs(stock, mods)
        self.assertEqual(merged, b"aXcdefgY")
        self.assertEqual(conflicts, [])
        self.assertEqual(len(runs), 2)
        self.assertEqual(diff.call_count, len(mods))


class SafetyTests(unittest.TestCase):
    def test_atomic_write_replaces_complete_file(self):
        d = Path(__file__).resolve().parent / "_work_atomic"
        shutil.rmtree(d, ignore_errors=True)
        target = d / "nested" / "file.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")
        atomic_write(target, b"new payload")
        self.assertEqual(target.read_bytes(), b"new payload")
        self.assertEqual(list(target.parent.glob("*.tmp")), [])
        shutil.rmtree(d, ignore_errors=True)

    def test_short_sealed_envelope_rejected(self):
        with self.assertRaises(MergeSafetyError):
            validate_sealed_input(b"too short", "test")

    def test_minimum_envelope_length_accepted(self):
        validate_sealed_input(b"x" * 48, "test")

    def test_transaction_rolls_back_if_a_write_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); first = root / 'first'; second = root / 'second'
            first.write_bytes(b'old first'); second.write_bytes(b'old second')
            calls = 0
            def writer(path, payload):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated failure')
                atomic_write(path, payload)
            with self.assertRaises(OSError):
                apply_file_transaction([(first, b'new first'), (second, b'new second')],
                                       root / 'journal.json', root / 'backup', writer=writer)
            self.assertEqual(first.read_bytes(), b'old first')
            self.assertEqual(second.read_bytes(), b'old second')
            self.assertFalse((root / 'journal.json').exists())

    def test_recovery_rolls_back_interrupted_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root / 'target'; backup = root / 'old'
            target.write_bytes(b'new'); backup.write_bytes(b'old')
            journal = root / 'journal.json'
            journal.write_text('{"state":"applying","files":[{"path":"' + str(target).replace('\\','\\\\') +
                               '","backup":"' + str(backup).replace('\\','\\\\') +
                               '","existed":true}]}', encoding='utf-8')
            self.assertEqual(recover_file_transaction(journal), 'rolled back')
            self.assertEqual(target.read_bytes(), b'old')


if __name__ == "__main__":
    unittest.main(verbosity=2)
