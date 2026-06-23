import unittest

from bc125at.channels import Channel
from bc125at.channels import is_valid_frequency
from bc125at.presets import (
    NORDBAYERN_FREENET,
    NORDBAYERN_PMR446,
    PRESET_CATALOG,
    get_preset_channels,
)
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


class PresetSafetyTests(unittest.TestCase):
    def test_all_presets_fit_scanner_limits(self):
        for key in PRESET_CATALOG:
            with self.subTest(preset=key):
                channels = get_preset_channels(key)
                self.assertTrue(channels)
                self.assertTrue(all(1 <= channel.index <= 500 for channel in channels))
                self.assertTrue(all(len(channel.name) <= 16 for channel in channels))
                self.assertTrue(all(is_valid_frequency(channel.frequency) for channel in channels))

    def test_german_licence_free_channel_sets_are_complete(self):
        self.assertEqual(len(NORDBAYERN_FREENET), 6)
        self.assertEqual(len(NORDBAYERN_PMR446), 16)
        self.assertLessEqual(max(freq for _, freq in NORDBAYERN_FREENET), 149.11875)

    def test_complete_nordbayern_preset_spans_three_banks(self):
        channels = get_preset_channels("nordbayern-all")

        self.assertEqual(len(channels), 130)
        self.assertEqual((channels[0].index, channels[-1].index), (1, 130))
        self.assertEqual({channel.bank for channel in channels}, {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
