import json

import numpy as np

from mvp_server.proof.witness_logger import WitnessLogger, WitnessPacket


def test_witness_logger_persists_tensor_and_meta(tmp_path) -> None:
    logger = WitnessLogger(str(tmp_path))
    packet = WitnessPacket(
        request_id="req-1",
        module_id="m1",
        x_pre=np.asarray([[1.0, 2.0]], dtype=np.float32),
        delta_post=np.asarray([[0.1, 0.2]], dtype=np.float32),
        h_x="hx",
        h_delta="hd",
        hash_schema_version=1,
    )

    record = logger.persist(packet)

    x = np.load(record.x_ref)
    delta = np.load(record.delta_ref)
    assert x.shape == (1, 2)
    assert delta.shape == (1, 2)

    with open(record.meta_ref, "r", encoding="utf-8") as handle:
        meta = json.load(handle)
    assert meta["request_id"] == "req-1"
    assert meta["h_x"] == "hx"
