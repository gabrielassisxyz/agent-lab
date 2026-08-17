"""What the seeded tracker may and may not carry.

The whole claim of `seed_tracker.py` is that a run reading its tracker learns nothing its prompt has
not already told it. That claim is only worth anything if it is enforced rather than intended, so
these are the cases where an intended version would still leak: a field added to the tracker
upstream, a bead whose completion record travels with it, a status that answers the question.
"""
import unittest

import seed_tracker
from bead_prompt import KEPT


# The real bead, with the fields that made this necessary. The comment text is the one that was
# actually in the tracker: it names the identifiers the canonical verification demands.
CLOSED_BEAD = {
    "id": "llmux-p4-two-phase-reservation-5vg",
    "title": "Two-phase reservation: pending slot, admission commit, finalization, dispatch",
    "issue_type": "task",
    "priority": 0,
    "labels": ["concurrency", "invariant", "phase-4"],
    "description": "The admission commit sits between the moment capacity is granted and …",
    "status": "closed",
    "closed_at": "2026-08-14T17:56:00Z",
    "close_reason": "completed",
    "comments": [{"author": "gabriel",
                  "text": "Completed by an agent. Implemented Reserve, PendingLease, and "
                          "ReservationOutcome in internal/route/reservation.go"}],
    "created_at": "2026-08-13T10:00:00Z",
    "updated_at": "2026-08-14T17:56:00Z",
    "dependencies": [], "dependents": [], "parent": None,
    "source_repo": "llmux", "compaction_level": 0,
}


class SeededRecord(unittest.TestCase):
    def test_the_completion_record_never_reaches_the_tracker(self):
        record = seed_tracker.build_record(CLOSED_BEAD)
        for leak in ("comments", "close_reason", "closed_at"):
            self.assertNotIn(leak, record)

    def test_the_bead_arrives_as_work_to_be_done(self):
        """A tracker that says the bead is closed answers the only question the run was asked."""
        self.assertEqual(seed_tracker.build_record(CLOSED_BEAD)["status"], "open")

    def test_it_carries_exactly_the_fields_the_prompt_shows(self):
        record = seed_tracker.build_record(CLOSED_BEAD)
        extra = set(record) - set(KEPT) - set(seed_tracker.STRUCTURAL) - {"status"}
        self.assertEqual(extra, set(), "the tracker may not say anything the prompt does not")
        self.assertEqual(record["id"], CLOSED_BEAD["id"])
        self.assertEqual(record["labels"], CLOSED_BEAD["labels"])

    def test_a_completion_field_added_to_the_whitelist_upstream_is_refused(self):
        """The reachable failure, and it is one edit away.

        The whitelist lives in `bead_prompt.py` and governs the prompt; this file borrows it. Add
        `comments` there - which reads like useful context for a task statement - and the leak
        arrives in the tracker silently. It has to be a refusal rather than a filter, because a
        filtered leak is one nobody goes looking for.
        """
        original = seed_tracker.KEPT
        seed_tracker.KEPT = original + ("comments",)
        self.addCleanup(setattr, seed_tracker, "KEPT", original)
        with self.assertRaises(ValueError):
            seed_tracker.build_record(CLOSED_BEAD)

    def test_a_resolution_note_added_upstream_is_refused_too(self):
        original = seed_tracker.KEPT
        seed_tracker.KEPT = original + ("resolution_notes",)
        self.addCleanup(setattr, seed_tracker, "KEPT", original)
        bead = dict(CLOSED_BEAD, resolution_notes="fixed by adding PendingLease")
        with self.assertRaises(ValueError):
            seed_tracker.build_record(bead)

    def test_a_bead_with_no_id_is_refused(self):
        with self.assertRaises(ValueError):
            seed_tracker.build_record({"title": "no id here"})


if __name__ == "__main__":
    unittest.main()
