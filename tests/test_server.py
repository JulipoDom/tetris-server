"""Behavioral checks for the local, single-match domain."""

import unittest
from dataclasses import FrozenInstanceError

from tetris_server.match import DomainError, MatchController
from tetris_shared.models import EndReason, MatchState, MessageType, Outcome


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.match = MatchController()
        self.a, self.b = object(), object()

    def pair(self):
        self.match.join(self.a, "Alice")
        return self.match.join(self.b, "Bob")

    def play(self):
        self.pair()
        self.match.ready(self.a)
        return self.match.ready(self.b)

    def test_identification_emits_only_opponent_nickname(self):
        self.assertEqual(self.match.state, MatchState.WAITING)
        self.assertIsNone(self.match.result)
        self.assertEqual(self.match.join(self.a, "same"), ())
        self.assertEqual(self.match.state, MatchState.WAITING)
        events = self.match.join(self.b, "same")
        self.assertEqual(self.match.state, MatchState.PREPARING)
        self.assertEqual([(e.recipient, e.kind, e.payload) for e in events],
                         [(self.a, MessageType.MATCH, "same"),
                          (self.b, MessageType.MATCH, "same")])

    def test_third_and_duplicate_sessions_preserve_pair(self):
        self.pair()
        original = (self.match.player1, self.match.player2)
        for session in (self.a, object()):
            with self.subTest(session=session), self.assertRaises(DomainError):
                self.match.join(session, "New")
            self.assertEqual((self.match.player1, self.match.player2), original)
            self.assertEqual(self.match.state, MatchState.PREPARING)

    def test_invalid_nicknames_and_unhashable_sessions_are_rejected(self):
        for nickname in ("", "a" * 21, "a b", "ç", "a|b", "a\n", None, 42):
            with self.subTest(nickname=nickname), self.assertRaises(DomainError):
                self.match.join(self.a, nickname)
        with self.assertRaises(DomainError):
            self.match.join([], "Alice")
        self.assertIsNone(self.match.player1)
        self.match.join(self.a, "A" * 20)

    def test_readiness_requires_pair_and_is_idempotent(self):
        self.match.join(self.a, "Alice")
        with self.assertRaises(DomainError):
            self.match.ready(self.a)
        self.match.join(self.b, "Bob")
        self.assertEqual(self.match.ready(self.a), ())
        self.assertTrue(self.match.player1.ready)
        self.assertFalse(self.match.player2.ready)
        self.assertEqual(self.match.ready(self.a), ())
        events = self.match.ready(self.b)
        self.assertEqual([(e.recipient, e.kind, e.payload) for e in events],
                         [(self.a, MessageType.READY, "GO"),
                          (self.b, MessageType.READY, "GO")])
        self.assertEqual(self.match.state, MatchState.PLAYING)
        self.assertEqual(self.match.ready(self.a), ())
        self.assertEqual(self.match.ready(self.b), ())

    def test_attacks_forward_garbage_unchanged_to_other_session(self):
        self.play()
        for session, opponent in ((self.a, self.b), (self.b, self.a)):
            for amount in (1, 2, 4):
                with self.subTest(amount=amount):
                    event, = self.match.attack(session, amount)
                    self.assertEqual((event.recipient, event.kind, event.payload),
                                     (opponent, MessageType.ATTACK, amount))

    def test_invalid_attack_values_have_no_effect(self):
        self.play()
        for amount in (True, False, 0, 3, -1, 5, 1.0, "1", None):
            with self.subTest(amount=amount), self.assertRaises(DomainError):
                self.match.attack(self.a, amount)
        self.assertEqual(self.match.state, MatchState.PLAYING)
        self.assertIsNone(self.match.result)

    def test_board_is_immutable_copy_without_inferring_defeat(self):
        self.play()
        cells = [[8] * 10 for _ in range(20)]
        event, = self.match.board(self.a, cells)
        self.assertEqual((event.recipient, event.kind), (self.b, MessageType.BOARD))
        self.assertIsInstance(event.payload, tuple)
        self.assertTrue(all(isinstance(row, tuple) for row in event.payload))
        cells[0][0] = 0
        self.assertEqual(event.payload[0][0], 8)
        self.assertEqual(self.match.player1.snapshot, event.payload)
        self.assertIsNone(self.match.result)
        self.assertEqual(self.match.state, MatchState.PLAYING)
        new, = self.match.board(self.a, [[0] * 10 for _ in range(20)])
        self.assertEqual(self.match.player1.snapshot, new.payload)
        self.assertEqual(event.payload[0][0], 8)

    def test_invalid_boards_do_not_replace_snapshot(self):
        self.play()
        self.match.board(self.a, [[0] * 10 for _ in range(20)])
        original = self.match.player1.snapshot
        # Include scalar and cell-type failures independently of dimensions.
        invalid = [None, "0" * 200, [], [[0] * 10] * 19,
                   [[0] * 9] * 20, [None] * 20]
        invalid += [[[value] * 10 for _ in range(20)]
                    for value in (-1, 9, True, False, 0.0, "0", None)]
        for cells in invalid:
            with self.subTest(cells=cells), self.assertRaises(DomainError):
                self.match.board(self.a, cells)
            self.assertEqual(self.match.player1.snapshot, original)

    def test_unknown_sessions_cannot_operate_in_any_phase(self):
        unknown = object()
        operations = [lambda: self.match.ready(unknown),
                      lambda: self.match.attack(unknown, 1),
                      lambda: self.match.board(unknown, [[0] * 10] * 20),
                      lambda: self.match.ko(unknown, "SPAWN"),
                      lambda: self.match.failure(unknown, EndReason.DISCONNECT)]
        for phase in ("waiting", "preparing", "playing", "finished"):
            if phase == "preparing": self.pair()
            if phase == "playing":
                self.match.ready(self.a)
                self.match.ready(self.b)
            if phase == "finished": self.match.ko(self.a, "SPAWN")
            for operation in operations:
                with self.subTest(phase=phase), self.assertRaises(DomainError):
                    operation()

    def test_game_effects_require_playing(self):
        for paired in (False, True):
            self.match = MatchController()
            self.match.join(self.a, "Alice")
            if paired: self.match.join(self.b, "Bob")
            for operation in (lambda: self.match.attack(self.a, 1),
                              lambda: self.match.board(self.a, [[0] * 10] * 20)):
                with self.subTest(paired=paired), self.assertRaises(DomainError):
                    operation()
            self.assertIsNone(self.match.result)

    def test_each_ko_order_records_first_loss_once(self):
        for first, second in ((self.a, self.b), (self.b, self.a)):
            self.match = MatchController()
            self.play()
            events = self.match.ko(first, "OVERFLOW")
            self.assertEqual(self.match.state, MatchState.FINISHED)
            result = self.match.result
            self.assertEqual(result.reason, EndReason.KO)
            self.assertEqual(result.outcome_for(first), Outcome.LOSE)
            self.assertEqual(result.outcome_for(second), Outcome.WIN)
            self.assertEqual({e.recipient: e.payload.outcome for e in events},
                             {first: Outcome.LOSE, second: Outcome.WIN})
            self.assertTrue(all(e.kind == MessageType.GAMEOVER for e in events))
            self.assertEqual(self.match.ko(second, "SPAWN"), ())
            self.assertIs(self.match.result, result)

    def test_invalid_ko_cause_leaves_active_match_intact(self):
        self.play()
        for cause in ("KO", "", None, 1):
            with self.subTest(cause=cause), self.assertRaises(DomainError):
                self.match.ko(self.a, cause)
        self.assertIsNone(self.match.result)

    def test_ko_before_play_is_protocol_failure(self):
        self.pair()
        events = self.match.ko(self.a, "SPAWN")
        self.assertEqual(self.match.result.reason, EndReason.PROTOCOL)
        self.assertEqual(self.match.result.outcome_for(self.a), Outcome.CANCEL)
        self.assertEqual([(e.recipient, e.payload.outcome) for e in events],
                         [(self.b, Outcome.CANCEL)])

    def test_identified_failures_cancel_before_play_and_award_during_play(self):
        for phase in ("waiting", "preparing", "playing"):
            for reason in (EndReason.DISCONNECT, EndReason.TIMEOUT, EndReason.PROTOCOL):
                with self.subTest(phase=phase, reason=reason):
                    self.match = MatchController()
                    self.match.join(self.a, "Alice")
                    if phase != "waiting": self.match.join(self.b, "Bob")
                    if phase == "playing":
                        self.match.ready(self.a)
                        self.match.ready(self.b)
                    events = self.match.failure(self.a, reason)
                    self.assertEqual(self.match.state, MatchState.FINISHED)
                    self.assertEqual(self.match.result.reason, reason)
                    self.assertEqual(self.match.result.outcome_for(self.a),
                                     Outcome.LOSE if phase == "playing" else Outcome.CANCEL)
                    if phase == "waiting": self.assertEqual(events, ())
                    else:
                        event, = events
                        self.assertEqual(event.recipient, self.b)
                        self.assertEqual(event.payload.outcome,
                                         Outcome.WIN if phase == "playing" else Outcome.CANCEL)
                        self.assertEqual(event.payload.reason, reason)

    def test_failure_reasons_are_restricted(self):
        self.play()
        for reason in (EndReason.KO, EndReason.SERVER_STOP, "BAD", None):
            with self.subTest(reason=reason), self.assertRaises(DomainError):
                self.match.failure(self.a, reason)
        self.assertIsNone(self.match.result)

    def test_planned_stop_cancels_in_every_phase(self):
        for count in (0, 1, 2, 3):
            with self.subTest(count=count):
                self.match = MatchController()
                if count >= 1: self.match.join(self.a, "Alice")
                if count >= 2: self.match.join(self.b, "Bob")
                if count == 3:
                    self.match.ready(self.a)
                    self.match.ready(self.b)
                events = self.match.stop()
                self.assertEqual(self.match.state, MatchState.FINISHED)
                self.assertEqual(self.match.result.reason, EndReason.SERVER_STOP)
                self.assertEqual(len(events), min(count, 2))
                self.assertTrue(all(e.payload.outcome == Outcome.CANCEL for e in events))

    def test_late_events_and_new_players_cannot_change_result(self):
        self.play()
        self.match.ko(self.a, "SPAWN")
        result = self.match.result
        for operation in (lambda: self.match.ready(self.a),
                          lambda: self.match.attack(self.a, 1),
                          lambda: self.match.board(self.a, [[0] * 10] * 20),
                          lambda: self.match.ko(self.b, "SPAWN"),
                          lambda: self.match.failure(self.b, EndReason.TIMEOUT),
                          self.match.stop):
            self.assertEqual(operation(), ())
            self.assertIs(self.match.result, result)
        with self.assertRaises(DomainError):
            self.match.join(object(), "New")

    def test_exposed_players_result_and_events_are_immutable(self):
        events = self.play()
        with self.assertRaises(FrozenInstanceError): self.match.player1.ready = False
        with self.assertRaises(FrozenInstanceError): events[0].payload = "PLAYER"
        self.match.ko(self.a, "SPAWN")
        with self.assertRaises(FrozenInstanceError): self.match.result.reason = EndReason.TIMEOUT
        self.assertIsInstance(self.match.result.outcomes, tuple)
        with self.assertRaises(AttributeError): self.match.state = MatchState.WAITING
        with self.assertRaises(AttributeError): self.match.result = None


if __name__ == "__main__":
    unittest.main()
