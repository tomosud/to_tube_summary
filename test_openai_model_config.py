import unittest

from openai_model_config import (
    DEFAULT_MODEL,
    calculate_usage_cost,
    get_model_pricing,
    resolve_models,
)


class ResolveModelsTest(unittest.TestCase):
    def test_auxiliary_model_follows_stage1(self):
        auxiliary, stage1, stage2 = resolve_models({
            "OPENAI_MODEL_STAGE1": "stage-1-model",
            "OPENAI_MODEL_STAGE2": "stage-2-model",
        })
        self.assertEqual(auxiliary, "stage-1-model")
        self.assertEqual(stage1, "stage-1-model")
        self.assertEqual(stage2, "stage-2-model")

    def test_explicit_general_model_overrides_auxiliary_only(self):
        auxiliary, stage1, stage2 = resolve_models({
            "OPENAI_MODEL": "aux-model",
            "OPENAI_MODEL_STAGE1": "stage-1-model",
            "OPENAI_MODEL_STAGE2": "stage-2-model",
        })
        self.assertEqual(auxiliary, "aux-model")
        self.assertEqual(stage1, "stage-1-model")
        self.assertEqual(stage2, "stage-2-model")

    def test_default_model_is_used_for_all_unconfigured_calls(self):
        self.assertEqual(resolve_models({}), (DEFAULT_MODEL, DEFAULT_MODEL, DEFAULT_MODEL))


class PricingTest(unittest.TestCase):
    def test_snapshot_uses_base_model_pricing(self):
        pricing = get_model_pricing("gpt-5.4-mini-2026-03-17")
        self.assertIsNotNone(pricing)
        self.assertEqual(pricing.input_per_million, 0.75)
        self.assertEqual(pricing.cached_input_per_million, 0.075)
        self.assertEqual(pricing.output_per_million, 4.50)

    def test_cost_separates_cached_input(self):
        cost = calculate_usage_cost(
            "gpt-5.4-mini-2026-03-17",
            input_tokens=1_000_000,
            cached_input_tokens=200_000,
            output_tokens=100_000,
        )
        self.assertAlmostEqual(cost, 1.065)

    def test_unknown_model_has_no_guessed_price(self):
        self.assertIsNone(calculate_usage_cost("unknown-model", 100, 100))


if __name__ == "__main__":
    unittest.main()
