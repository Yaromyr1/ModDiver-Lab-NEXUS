import unittest

import log_events


class LogEventsTests(unittest.TestCase):
    def test_successful_empty_purge_and_library_cleanup_are_green(self):
        for text in ('nothing deployed',
                     'completely purged the mod library; game files and deployment backups were not changed'):
            self.assertEqual(log_events.classify(text), 'success')

    def test_cleanup_errors_keep_error_priority(self):
        self.assertEqual(log_events.classify('completely purged failed'), 'error')
        self.assertEqual(log_events.classify('nothing deployed: could not restore backup'), 'error')


    def test_repair_result_levels(self):
        self.assertEqual(log_events.classify('BUILT-IN MODS REPAIRED/UPDATED SUCCESSFULLY'), 'success')
        self.assertEqual(log_events.classify('FAILED TO REPAIR/UPDATE BUILT-IN MODS'), 'error')
        self.assertEqual(log_events.classify('REPAIRED AND UPDATED SUCCESFULLY'), 'success')
        self.assertEqual(log_events.classify('FAILED TO REPAIR OR UPDATE'), 'error')
        self.assertEqual(log_events.classify('PREVIEW COMPLETE: 3 FILE(S) WOULD BE INSTALLED; 0 FAILED/SKIPPED. NO GAME FILES CHANGED.'), 'success')
