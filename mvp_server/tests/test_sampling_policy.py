from mvp_server.proof.sampling_policy import SamplingPolicy


def test_every_request_mode_always_samples() -> None:
    policy = SamplingPolicy(mode="every_request")
    assert policy.should_sample("req-1", "module-a")
    assert policy.should_sample("req-2", "module-a")


def test_sampled_mode_is_deterministic() -> None:
    policy = SamplingPolicy(mode="sampled", sample_n=8)
    first = policy.should_sample("req-123", "module-a")
    second = policy.should_sample("req-123", "module-a")
    assert first == second

