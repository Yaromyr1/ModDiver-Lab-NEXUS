import unittest
from unittest.mock import patch

import portable_hash
import dlbin_codec


class HashCacheTests(unittest.TestCase):
    def test_original_hash_vectors_at_word_boundaries(self):
        vectors = {0: 0xd9f18670253a13e6, 1: 0xe42a91c817c26bb,
                   7: 0x1e172428b0cd4ba5, 8: 0x53d78119f7fa454,
                   9: 0xdd249516ea8bf43d, 127: 0x481cb49e1c8e4852,
                   128: 0x2f4d5aec8c49cbd0, 129: 0x9f4a54d642565816,
                   4097: 0xf16ed90cbcff2fe1}
        portable_hash._HASH_CACHE.clear()
        for size, expected in vectors.items():
            raw = bytes(i % 251 for i in range(size))
            self.assertEqual(dlbin_codec.content_hash(raw), expected)
            with patch.object(portable_hash, 'forward', side_effect=AssertionError('must reuse hash')):
                self.assertEqual(portable_hash.content_hash(raw), expected)

    def test_mutated_bytes_are_rehashed_and_cache_remains_small(self):
        portable_hash._HASH_CACHE.clear()
        raw = bytearray(range(128))
        original = portable_hash.content_hash(raw)
        raw[64] ^= 1
        self.assertNotEqual(portable_hash.content_hash(raw), original)
        raw[64] ^= 1
        self.assertEqual(portable_hash.content_hash(raw), original)
        for i in range(40):
            portable_hash.content_hash(bytes([i])*100)
        self.assertLessEqual(len(portable_hash._HASH_CACHE), 32)
        self.assertTrue(all(len(key[1]) == 32 for key in portable_hash._HASH_CACHE))
