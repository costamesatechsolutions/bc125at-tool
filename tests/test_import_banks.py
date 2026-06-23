import unittest

from bc125at.channels import Channel
from bc125at.web.app import _apply_import_options, _build_import_preview


class ImportBankTests(unittest.TestCase):
    def test_bank_three_maps_to_channels_101_through_150(self):
        channels = [Channel(index=1, frequency=146.52), Channel(index=2, frequency=162.55)]

        remapped, truncated = _apply_import_options(channels, target_bank=3)

        self.assertEqual([channel.index for channel in remapped], [101, 102])
        self.assertIsNone(truncated)

    def test_bank_zero_maps_to_channels_451_through_500(self):
        channels = [Channel(index=1, frequency=146.52)]

        remapped, _ = _apply_import_options(channels, target_bank=0)

        self.assertEqual(remapped[0].index, 451)
        self.assertEqual(remapped[0].bank, 0)

    def test_preview_preserves_confirm_options(self):
        channels = [Channel(index=101, frequency=146.52)]

        preview = _build_import_preview(
            channels,
            target_bank=3,
            clear_bank_first=True,
        )

        self.assertEqual(preview["bank_target"], "3")
        self.assertTrue(preview["clear_bank_first"])


if __name__ == "__main__":
    unittest.main()
