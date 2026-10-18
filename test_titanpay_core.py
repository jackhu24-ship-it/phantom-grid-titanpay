#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHANToM GRID // TitanPay Unit & Invariant Audit Suite
Tournament: PayPal AI Hackathon 2026
Validates:
1. Atomic 1-Transaction DvP Settlement
2. Sum(Net)=0 Conservation Invariant across 1,000 cycles
3. Timeout Atomic Reclaim & Zero Capital Lockup
4. PayPal Sandbox Orders API v2 Payload Integration
5. ZDR 2-Pass Memory Wipe == 0.000000 MB Residue
"""

import sys
import time
from pathlib import Path
import pytest

# Add current folder to path
sys.path.insert(0, str(Path(__file__).parent))
from titanpay_core import TitanPayDvPEngine, DvPState


def test_atomic_dvp_settlement_happy_path():
    engine = TitanPayDvPEngine()
    init_total = engine.get_total_system_capital()

    escrow_id = engine.create_dvp_escrow("Agent_Alpha", "Agent_Beta", 1000.0, "DATASET_LICENSE")
    assert engine.escrows[escrow_id]["state"] == DvPState.STANDBY

    funded = engine.fund_escrow(escrow_id)
    assert funded is True
    assert engine.escrows[escrow_id]["state"] == DvPState.FUNDED
    assert engine.ledgers["Escrow_Vault"] == 1000.0

    settled, msg = engine.execute_atomic_settlement(escrow_id)
    assert settled is True
    assert msg == "SUCCESS_SETTLED"
    assert engine.escrows[escrow_id]["state"] == DvPState.DISPATCHED
    assert engine.ledgers["Escrow_Vault"] == 0.0
    assert engine.ledgers["Agent_Beta"] == 51000.0

    assert abs(engine.get_total_system_capital() - init_total) < 1e-6


def test_timeout_atomic_reclaim():
    engine = TitanPayDvPEngine()
    init_buyer = engine.ledgers["Agent_Alpha"]

    # Short timeout
    escrow_id = engine.create_dvp_escrow("Agent_Alpha", "Agent_Beta", 5000.0, "ORPHANED_LEG", timeout_seconds=0.01)
    engine.fund_escrow(escrow_id)
    assert engine.ledgers["Agent_Alpha"] == init_buyer - 5000.0

    # Wait for timeout
    time.sleep(0.02)
    settled, msg = engine.execute_atomic_settlement(escrow_id)
    assert settled is True
    assert "RECLAIMED_TIMEOUT_EXPIRED" in msg
    assert engine.escrows[escrow_id]["state"] == DvPState.RECLAIMED
    # 100% Capital returned to buyer
    assert engine.ledgers["Agent_Alpha"] == init_buyer
    assert engine.ledgers["Escrow_Vault"] == 0.0


def test_sum_net_zero_chaos_1000_cycles():
    engine = TitanPayDvPEngine()
    init_total = engine.get_total_system_capital()

    for i in range(1000):
        amount = 10.0 + (i % 50)
        escrow_id = engine.create_dvp_escrow("Agent_Alpha", "Agent_Beta", amount, f"ITEM_{i}")
        engine.fund_escrow(escrow_id)
        if i % 5 == 0:
            # Reclaim
            engine.reclaim_escrow_funds(escrow_id, reason="CHAOS_ABORT")
        else:
            # Settle
            engine.execute_atomic_settlement(escrow_id)

    # Invariant assertion
    assert abs(engine.get_total_system_capital() - init_total) < 1e-6
    assert engine.ledgers["Escrow_Vault"] == 0.0


def test_paypal_sandbox_payload():
    engine = TitanPayDvPEngine()
    escrow_id = engine.create_dvp_escrow("Agent_Alpha", "Agent_Beta", 350.0, "API_CALL_TOKEN")
    paypal_order = engine.escrows[escrow_id]["paypal_order"]
    assert "id" in paypal_order
    assert paypal_order["status"] == "CREATED"
    assert paypal_order["purchase_units"][0]["amount"]["value"] == "350.00"


def test_zdr_zero_residue():
    engine = TitanPayDvPEngine()
    res = engine.perform_zdr_scrubbing()
    assert res == 0.000000
