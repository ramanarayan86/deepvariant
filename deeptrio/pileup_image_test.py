# Copyright 2017 Google LLC.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Tests for deeptrio.pileup_image."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import sys
if 'google' in sys.modules and 'google.protobuf' not in sys.modules:
  del sys.modules['google']


import itertools



from absl.testing import absltest
from absl.testing import parameterized
import mock
import numpy as np
import numpy.testing as npt

from third_party.nucleus.io import fasta
from third_party.nucleus.protos import reads_pb2
from third_party.nucleus.protos import variants_pb2
from third_party.nucleus.testing import test_utils
from third_party.nucleus.util import ranges

from deeptrio import pileup_image
from deepvariant.protos import deepvariant_pb2
from deepvariant.python import pileup_image_native


def _supporting_reads(*names):
  return deepvariant_pb2.DeepVariantCall.SupportingReads(read_names=names)


def _make_dv_call(ref_bases='A', alt_bases='C'):
  return deepvariant_pb2.DeepVariantCall(
      variant=variants_pb2.Variant(
          reference_name='chr1',
          start=10,
          end=11,
          reference_bases=ref_bases,
          alternate_bases=[alt_bases]),
      allele_support={'C': _supporting_reads('read1/1', 'read2/1')})


def _make_encoder(read_requirements=None, **kwargs):
  """Make a PileupImageEncoderNative with overrideable default options."""
  options = pileup_image.default_options(read_requirements)
  options.MergeFrom(deepvariant_pb2.PileupImageOptions(**kwargs))
  return pileup_image_native.PileupImageEncoderNative(options)


def _make_image_creator(ref_reader, sam_reader_obj, **kwargs):
  options = pileup_image.default_options()
  options.MergeFrom(deepvariant_pb2.PileupImageOptions(**kwargs))
  return pileup_image.PileupImageCreator(options, ref_reader, sam_reader_obj)


class PileupImageEncoderTest(parameterized.TestCase):

  def setUp(self):
    super(PileupImageEncoderTest, self).setUp()
    self.options = pileup_image.default_options()

  @parameterized.parameters(('A', 250), ('G', 180), ('T', 100), ('C', 30),
                            ('N', 0), ('X', 0))
  def test_base_color(self, base, expected_color):
    pie = _make_encoder(
        base_color_offset_a_and_g=40,
        base_color_offset_t_and_c=30,
        base_color_stride=70)
    self.assertAlmostEqual(pie.base_color(base), expected_color)

  @parameterized.parameters(
      (0, 0),
      (5, int(254 * 0.25)),
      (10, int(254 * 0.5)),
      (15, int(254 * 0.75)),
      (19, int(254 * 0.95)),
      (20, 254),
      (21, 254),
      (25, 254),
      (40, 254),
  )
  def test_base_quality_color(self, base_qual, expected_color):
    pie = _make_encoder(base_quality_cap=20)
    self.assertAlmostEqual(pie.base_quality_color(base_qual), expected_color)

  @parameterized.parameters(
      (0, 0),
      (5, int(254 * 0.25)),
      (10, int(254 * 0.5)),
      (15, int(254 * 0.75)),
      (19, int(254 * 0.95)),
      (20, 254),
      (21, 254),
      (25, 254),
      (40, 254),
  )
  def test_mapping_quality_color(self, mapping_qual, expected_color):
    pie = _make_encoder(mapping_quality_cap=20)
    self.assertAlmostEqual(
        pie.mapping_quality_color(mapping_qual), expected_color)

  @parameterized.parameters((True, 1), (False, 2))
  def test_strand_color(self, on_positive_strand, expected_color):
    pie = _make_encoder(positive_strand_color=1, negative_strand_color=2)
    self.assertAlmostEqual(pie.strand_color(on_positive_strand), expected_color)

  @parameterized.parameters(
      (False, int(254.0 * 0.2)),
      (True, int(254.0 * 0.1)),
  )
  def test_supports_alt_color(self, supports_alt, expected_color):
    pie = _make_encoder(
        allele_supporting_read_alpha=0.1, allele_unsupporting_read_alpha=0.2)
    self.assertAlmostEqual(pie.supports_alt_color(supports_alt), expected_color)

  @parameterized.parameters(
      (False, int(254.0 * 0.4)),
      (True, int(254.0 * 0.3)),
  )
  def test_matches_ref_color(self, matches_ref, expected_color):
    pie = _make_encoder(
        reference_matching_read_alpha=0.3, reference_mismatching_read_alpha=0.4)
    self.assertAlmostEqual(pie.matches_ref_color(matches_ref), expected_color)

  def test_reference_encoding(self):
    self.assertImageRowEquals(
        _make_encoder().encode_reference('ACGTN'),
        np.dstack([
            # Base.
            (250, 30, 180, 100, 0),
            # Base quality.
            (254, 254, 254, 254, 254),
            # Mapping quality.
            (254, 254, 254, 254, 254),
            # Strand channel (forward or reverse)
            (70, 70, 70, 70, 70),
            # Supports alt or not.
            (152, 152, 152, 152, 152),
            # Matches ref or not.
            (50, 50, 50, 50, 50)
        ]).astype(np.uint8))

  def assertImageRowEquals(self, image_row, expected):
    npt.assert_equal(image_row, expected.astype(np.uint8))

  def test_encode_read_matches(self):
    start = 10
    dv_call = _make_dv_call()
    alt_allele = dv_call.variant.alternate_bases[0]
    read = test_utils.make_read(
        'ACCGT', start=start, cigar='5M', quals=range(10, 15), name='read1')
    full_expected = np.dstack([
        # Base.
        (250, 30, 30, 180, 100),
        # Base quality.
        (63, 69, 76, 82, 88),
        # Mapping quality.
        (211, 211, 211, 211, 211),
        # Strand channel (forward or reverse)
        (70, 70, 70, 70, 70),
        # Supports alt or not.
        (254, 254, 254, 254, 254),
        # Matches ref or not.
        (50, 50, 254, 50, 50)
    ]).astype(np.uint8)

    self.assertImageRowEquals(
        _make_encoder().encode_read(dv_call, 'ACAGT', read, start, alt_allele),
        full_expected)

  # pylint:disable=g-complex-comprehension
  @parameterized.parameters((bases_start, bases_end)
                            for bases_start in range(0, 5)
                            for bases_end in range(6, 12))
  # pylint:enable=g-complex-comprehension
  def test_encode_read_spans2(self, bases_start, bases_end):
    bases = 'AAAACCGTCCC'
    quals = [9, 9, 9, 10, 11, 12, 13, 14, 8, 8, 8]
    bases_start_offset = 7
    ref_start = 10
    ref_size = 5
    read_bases = bases[bases_start:bases_end]
    read_quals = quals[bases_start:bases_end]
    read_start = bases_start_offset + bases_start

    # Create our expected image row encoding.
    full_expected = np.dstack([
        # Base.
        (250, 30, 30, 180, 100),
        # Base quality.
        (63, 69, 76, 82, 88),
        # Mapping quality.
        (211, 211, 211, 211, 211),
        # Strand channel (forward or reverse)
        (70, 70, 70, 70, 70),
        # Supports alt or not.
        (254, 254, 254, 254, 254),
        # Matches ref or not.
        (50, 50, 254, 50, 50)
    ]).astype(np.uint8)
    expected = np.zeros((1, ref_size, self.options.num_channels),
                        dtype=np.uint8)
    for i in range(read_start, read_start + len(read_bases)):
      if ref_start <= i < ref_start + ref_size:
        expected[0, i - ref_start] = full_expected[0, i - ref_start]

    read = test_utils.make_read(
        read_bases,
        start=read_start,
        cigar=str(len(read_bases)) + 'M',
        quals=read_quals,
        name='read1')
    dv_call = _make_dv_call()
    alt_allele = dv_call.variant.alternate_bases[0]
    self.assertImageRowEquals(
        _make_encoder().encode_read(dv_call, 'ACAGT', read, ref_start,
                                    alt_allele), expected)

  def test_encode_read_deletion(self):
    # ref:  AACAG
    # read: AA--G
    start = 2
    read = test_utils.make_read(
        'AAG', start=start, cigar='2M2D1M', quals=range(10, 13), name='read1')
    dv_call = _make_dv_call()
    alt_allele = dv_call.variant.alternate_bases[0]
    full_expected = np.dstack([
        # Base. The second A is 0 because it's the anchor of the deletion.
        (250, 0, 0, 0, 180),
        # Base quality.
        (63, 69, 0, 0, 76),
        # Mapping quality.
        (211, 211, 0, 0, 211),
        # Strand channel (forward or reverse)
        (70, 70, 0, 0, 70),
        # Supports alt or not.
        (254, 254, 0, 0, 254),
        # Matches ref or not.
        (50, 254, 0, 0, 50)
    ]).astype(np.uint8)
    self.assertImageRowEquals(
        _make_encoder().encode_read(dv_call, 'AACAG', read, start, alt_allele),
        full_expected)

  def test_encode_read_insertion(self):
    # ref:  AA-CAG
    # read: AAACAG
    start = 2
    read = test_utils.make_read(
        'AAACAG',
        start=start,
        cigar='2M1I3M',
        quals=range(10, 16),
        name='read1')
    dv_call = _make_dv_call()
    alt_allele = dv_call.variant.alternate_bases[0]
    full_expected = np.dstack([
        # Base.
        (250, 0, 30, 250, 180),
        # Base quality.
        (63, 76, 82, 88, 95),
        # Mapping quality.
        (211, 211, 211, 211, 211),
        # Strand channel (forward or reverse)
        (70, 70, 70, 70, 70),
        # Supports alt or not.
        (254, 254, 254, 254, 254),
        # Matches ref or not.
        (50, 254, 50, 50, 50)
    ]).astype(np.uint8)
    self.assertImageRowEquals(
        _make_encoder().encode_read(dv_call, 'AACAG', read, start, alt_allele),
        full_expected)

  @parameterized.parameters(
      (min_base_qual, min_mapping_qual)
      for min_base_qual, min_mapping_qual in itertools.product(
          range(0, 5), range(0, 5)))
  def test_ignores_reads_with_low_quality_bases(self, min_base_qual,
                                                min_mapping_qual):
    """Check that we discard reads with low quality bases at variant start site.

    We have the following scenario:

    position    0    1    2    3    4    5
    reference        A    A    C    A    G
    read             A    A    A
    variant               C

    We set the base quality of the middle base in the read to different values
    of `base_qual`. Since the middle position of the read is where the variant
    starts, the read should only be kept if `base_qual` >= `min_base_qual`.

    Args:
      min_base_qual: Reads are discarded if the base at a variant start position
        does not meet this base quality requirement.
      min_mapping_qual: Reads are discarded if they do not meet this mapping
        quality requirement.
    """
    dv_call = deepvariant_pb2.DeepVariantCall(
        variant=variants_pb2.Variant(
            reference_name='chr1',
            start=2,
            end=3,
            reference_bases='A',
            alternate_bases=['C']))

    read_requirements = reads_pb2.ReadRequirements(
        min_base_quality=min_base_qual,
        min_mapping_quality=min_mapping_qual,
        min_base_quality_mode=reads_pb2.ReadRequirements.ENFORCED_BY_CLIENT)
    pie = _make_encoder(read_requirements=read_requirements)

    for base_qual in range(min_base_qual + 5):
      quals = [min_base_qual, base_qual, min_base_qual]
      read = test_utils.make_read(
          'AAA', start=1, cigar='3M', quals=quals, mapq=min_mapping_qual)
      actual = pie.encode_read(dv_call, 'AACAG', read, 1, 'C')
      if base_qual < min_base_qual:
        self.assertIsNone(actual)
      else:
        self.assertIsNotNone(actual)

  @parameterized.parameters(
      (min_base_qual, min_mapping_qual)
      for min_base_qual, min_mapping_qual in itertools.product(
          range(0, 5), range(0, 5)))
  def test_keeps_reads_with_low_quality_bases(self, min_base_qual,
                                              min_mapping_qual):
    """Check that we keep reads with adequate quality at variant start position.

    We have the following scenario:

    position    0    1    2    3    4    5
    reference        A    A    C    A    G
    read             A    A    A
    variant               C

    We set the base quality of the first and third bases in the read to
    different functions of `base_qual`. The middle position of the read is
    where the variant starts, and this position always has base quality greater
    than `min_base_qual`. Thus, the read should always be kept.

    Args:
      min_base_qual: Reads are discarded if the base at a variant start position
        does not meet this base quality requirement.
      min_mapping_qual: Reads are discarded if they do not meet this mapping
        quality requirement.
    """
    dv_call = deepvariant_pb2.DeepVariantCall(
        variant=variants_pb2.Variant(
            reference_name='chr1',
            start=2,
            end=3,
            reference_bases='A',
            alternate_bases=['C']))

    read_requirements = reads_pb2.ReadRequirements(
        min_base_quality=min_base_qual,
        min_mapping_quality=min_mapping_qual,
        min_base_quality_mode=reads_pb2.ReadRequirements.ENFORCED_BY_CLIENT)
    pie = _make_encoder(read_requirements=read_requirements)

    for base_qual in range(min_base_qual + 5):
      quals = [base_qual - 1, min_base_qual, base_qual + 1]
      read = test_utils.make_read(
          'AAA', start=1, cigar='3M', quals=quals, mapq=min_mapping_qual)
      actual = pie.encode_read(dv_call, 'AACAG', read, 1, 'C')
      self.assertIsNotNone(actual)

  @parameterized.parameters(
      (min_base_qual, min_mapping_qual)
      for min_base_qual, min_mapping_qual in itertools.product(
          range(0, 5), range(0, 5)))
  def test_ignores_reads_with_low_mapping_quality(self, min_base_qual,
                                                  min_mapping_qual):
    """Check that we discard reads with low mapping quality.

    We have the following scenario:

    position    0    1    2    3    4    5
    reference        A    A    C    A    G
    read             A    A    A
    variant               C

    We set the mapping quality of the read to different values of
    `mapping_qual`. All bases in the read have base quality greater than
    `min_base_qual`. The read should only be kept if
    `mapping_qual` > `min_mapping_qual`.

    Args:
      min_base_qual: Reads are discarded if the base at a variant start position
        does not meet this base quality requirement.
      min_mapping_qual: Reads are discarded if they do not meet this mapping
        quality requirement.
    """
    dv_call = deepvariant_pb2.DeepVariantCall(
        variant=variants_pb2.Variant(
            reference_name='chr1',
            start=2,
            end=3,
            reference_bases='A',
            alternate_bases=['C']))

    read_requirements = reads_pb2.ReadRequirements(
        min_base_quality=min_base_qual,
        min_mapping_quality=min_mapping_qual,
        min_base_quality_mode=reads_pb2.ReadRequirements.ENFORCED_BY_CLIENT)
    pie = _make_encoder(read_requirements=read_requirements)

    for mapping_qual in range(min_mapping_qual + 5):
      quals = [min_base_qual, min_base_qual, min_base_qual]
      read = test_utils.make_read(
          'AAA', start=1, cigar='3M', quals=quals, mapq=mapping_qual)
      actual = pie.encode_read(dv_call, 'AACAG', read, 1, 'C')
      if mapping_qual < min_mapping_qual:
        self.assertIsNone(actual)
      else:
        self.assertIsNotNone(actual)

  @parameterized.parameters(
      # alt_allele is C, supported by only frag 1 of read1 and frag 2 of read 3.
      ('read1', 1, 'C', 'C', True),
      ('read1', 2, 'C', 'C', False),
      ('read2', 1, 'C', 'G', False),
      ('read2', 2, 'C', 'G', False),
      ('read3', 1, 'C', 'C', False),
      ('read3', 2, 'C', 'C', True),
      # alt_allele is now G, so only read2 (both frags) support alt.
      ('read1', 1, 'G', 'C', False),
      ('read1', 2, 'G', 'C', False),
      ('read2', 1, 'G', 'G', True),
      ('read2', 2, 'G', 'G', True),
      ('read3', 1, 'G', 'C', False),
      ('read3', 2, 'G', 'C', False),
  )
  def test_read_support_is_respected(self, read_name, read_number, alt_allele,
                                     read_base, supports_alt):
    """supports_alt is encoded as the 5th channel out of the 7 channels."""
    dv_call = deepvariant_pb2.DeepVariantCall(
        variant=variants_pb2.Variant(
            reference_name='chr1',
            start=10,
            end=11,
            reference_bases='A',
            alternate_bases=[alt_allele]),
        allele_support={
            'C': _supporting_reads('read1/1', 'read3/2'),
            'G': _supporting_reads('read2/1', 'read2/2'),
        })
    read = test_utils.make_read(
        read_base,
        start=dv_call.variant.start,
        cigar='1M',
        quals=[50],
        name=read_name)
    read.read_number = read_number
    actual = _make_encoder().encode_read(dv_call, 'TAT', read,
                                         dv_call.variant.start - 1, alt_allele)
    expected_base_values = {'C': 30, 'G': 180}
    expected_supports_alt_channel = [152, 254]
    expected = [
        expected_base_values[read_base], 254, 211, 70,
        expected_supports_alt_channel[supports_alt], 254
    ]

    self.assertEqual(list(actual[0, 1]), expected)


class PileupImageCreatorEncodePileupTest(parameterized.TestCase):
  """Tests of PileupImageCreator build_pileup routine."""

  def setUp(self):
    super(PileupImageCreatorEncodePileupTest, self).setUp()
    self.alt_allele = 'C'
    self.dv_call = _make_dv_call(ref_bases='G', alt_bases=self.alt_allele)
    self.pic = _make_image_creator(
        None, None, width=3, height=4, reference_band_height=2)
    self.ref = 'AGC'
    self.read1 = test_utils.make_read('AGC', start=0, cigar='3M', name='read1')
    self.read2 = test_utils.make_read('AGC', start=1, cigar='3M', name='read2')
    self.read3 = test_utils.make_read('AGC', start=2, cigar='3M', name='read3')
    self.read4 = test_utils.make_read('AGC', start=3, cigar='3M', name='read4')

    self.expected_rows = {
        'ref':
            np.asarray(range(0, 3 * self.pic.num_channels),
                       np.uint8).reshape(1, 3, self.pic.num_channels),
        'empty':
            np.zeros((1, 3, self.pic.num_channels), dtype=np.uint8),
        'read1':
            np.full((1, 3, self.pic.num_channels), 1, dtype=np.uint8),
        'read2':
            np.full((1, 3, self.pic.num_channels), 2, dtype=np.uint8),
        'read3':
            None,
        'read4':
            np.full((1, 3, self.pic.num_channels), 3, dtype=np.uint8),
        'read5':
            np.full((1, 3, self.pic.num_channels), 3, dtype=np.uint8),
    }

    # Setup our shared mocks.
    mock_encoder = mock.Mock(spec=['encode_read', 'encode_reference'])
    mock_encoder.encode_reference.return_value = self.expected_rows['ref']

    # pylint: disable=unused-argument
    def get_read_row(dv_call, refbases, read, pos, alt_allele):
      return self.expected_rows[read.fragment_name]

    mock_encoder.encode_read.side_effect = get_read_row

    self.mock_enc_ref = mock_encoder.encode_reference
    self.mock_enc_read = mock_encoder.encode_read

    self.pic._encoder = mock_encoder

  def assertImageMatches(self, actual_image, *row_names):
    """Checks that actual_image matches an image from constructed row_names."""
    self.assertEqual(actual_image.shape,
                     (self.pic.height, self.pic.width, self.pic.num_channels))
    expected_image = np.vstack([self.expected_rows[name] for name in row_names])
    npt.assert_equal(actual_image, expected_image)

  def test_image_no_reads(self):
    # This image is created just from reference and no reads. Checks that the
    # function is listening to all of our image creation parameters (e.g.,
    # reference_band_height, width, height, etc) and is filling the image with
    # empty rows when it runs out of reads.
    image = self.pic.build_pileup(self.dv_call, self.ref, [], {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    test_utils.assert_not_called_workaround(self.mock_enc_read)
    self.assertImageMatches(image, 'ref', 'ref', 'empty', 'empty')

  def test_image_one_read(self):
    # We add a single read to our image.
    image = self.pic.build_pileup(self.dv_call, self.ref, [self.read1],
                                  {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    self.mock_enc_read.assert_called_once_with(self.dv_call, self.ref,
                                               self.read1, 9, {self.alt_allele})
    self.assertImageMatches(image, 'ref', 'ref', 'read1', 'empty')

  def test_image_creation_with_more_reads_than_rows(self):
    # Read1 should be dropped because there's only space for Read2 and Read4.
    # If there are more reads than rows, a deterministic random subset is used.
    image = self.pic.build_pileup(self.dv_call, self.ref,
                                  [self.read1, self.read2, self.read4],
                                  {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4, 9, {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read2', 'read4')

  def test_image_creation_with_bad_read(self):
    # Read 3 is bad (return value is None) so it should be skipped.
    image = self.pic.build_pileup(self.dv_call, self.ref,
                                  [self.read1, self.read3, self.read2],
                                  {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read1', 'read2')

  def test_image_creation_with_all_reads_in_new_order(self):
    # Read 3 is bad (return value is None) so it should be skipped. Read2 should
    # also be dropped because there's only space for Read1 and Read4. If there
    # are more reads than rows, a deterministic random subset is used.
    image = self.pic.build_pileup(
        self.dv_call, self.ref,
        [self.read2, self.read3, self.read4, self.read1], {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read1', 'read4')

  @parameterized.parameters(
      (True, ['ref', 'ref', 'read2', 'read4', 'read1', 'read5']),
      (False, ['ref', 'ref', 'read1', 'read2', 'read4', 'read5']))
  def test_image_creation_with_haplotype_sorting(self, sort_by_haplotypes,
                                                 expected_reads_layout):
    # There are 4 reads. They are expected to be sorted by HP tag.

    read1 = test_utils.make_read('AGC', start=0, cigar='3M', name='read1')
    read1.info['HP'].values.add().int_value = 2
    read2 = test_utils.make_read('AGC', start=1, cigar='3M', name='read2')
    read2.info['HP'].values.add().int_value = 1
    read4 = test_utils.make_read('AGC', start=3, cigar='3M', name='read4')
    read4.info['HP'].values.add().int_value = 1
    read5 = test_utils.make_read('AGC', start=4, cigar='3M', name='read5')
    read5.info['HP'].values.add().int_value = 2

    # Change height to 6 so that we have at least 4 rows for reads to test
    # sorting by haplotypes.
    self.pic.height = 6
    # Change options to set sort_by_haplotypes flag.
    self.pic._options.sort_by_haplotypes = sort_by_haplotypes
    image = self.pic.build_pileup(self.dv_call, self.ref,
                                  [read1, read2, read4, read5],
                                  {self.alt_allele})
    self.mock_enc_ref.assert_called_once_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, read4, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, read5, 9, {self.alt_allele}),
    ])

    self.assertEqual(image.shape,
                     (self.pic.height, self.pic.width, self.pic.num_channels))
    expected_image = np.vstack(
        [self.expected_rows[name] for name in expected_reads_layout])
    npt.assert_equal(image, expected_image)


class PileupImageForTrioCreatorEncodePileupTest(parameterized.TestCase):
  """Tests of PileupImageCreator build_pileup routine for Trio."""

  def setUp(self):
    super(PileupImageForTrioCreatorEncodePileupTest, self).setUp()
    self.alt_allele = 'C'
    self.dv_call = _make_dv_call(ref_bases='G', alt_bases=self.alt_allele)
    self.pic = _make_image_creator(
        None,
        None,
        width=3,
        height_parent=4,
        height_child=4,
        reference_band_height=2,
        sequencing_type=deepvariant_pb2.PileupImageOptions.TRIO)
    self.ref = 'AGC'

    self.read1 = test_utils.make_read('AGC', start=0, cigar='3M', name='read1')
    self.read2 = test_utils.make_read('AGC', start=1, cigar='3M', name='read2')
    self.read3 = test_utils.make_read('AGC', start=2, cigar='3M', name='read3')
    self.read4 = test_utils.make_read('AGC', start=3, cigar='3M', name='read4')

    self.read1_parent1 = test_utils.make_read(
        'TGC', start=0, cigar='3M', name='read1')
    self.read2_parent1 = test_utils.make_read(
        'TGC', start=1, cigar='3M', name='read2')
    self.read3_parent1 = test_utils.make_read(
        'AGC', start=2, cigar='3M', name='read3')
    self.read4_parent1 = test_utils.make_read(
        'AGC', start=3, cigar='3M', name='read4')

    self.read1_parent2 = test_utils.make_read(
        'AGC', start=0, cigar='3M', name='read1')
    self.read2_parent2 = test_utils.make_read(
        'AGC', start=1, cigar='3M', name='read2')
    self.read3_parent2 = test_utils.make_read(
        'AGC', start=2, cigar='3M', name='read3')
    self.read4_parent2 = test_utils.make_read(
        'AGC', start=3, cigar='3M', name='read4')

    self.expected_rows = {
        'ref':
            np.asarray(range(0, 3 * self.pic.num_channels),
                       np.uint8).reshape(1, 3, self.pic.num_channels),
        'empty':
            np.zeros((1, 3, self.pic.num_channels), dtype=np.uint8),
        'read1_parent1':
            np.full((1, 3, self.pic.num_channels), 1, dtype=np.uint8),
        'read2_parent1':
            np.full((1, 3, self.pic.num_channels), 2, dtype=np.uint8),
        'read3_parent1':
            None,
        'read4_parent1':
            np.full((1, 3, self.pic.num_channels), 3, dtype=np.uint8),
        'read1':
            np.full((1, 3, self.pic.num_channels), 1, dtype=np.uint8),
        'read2':
            np.full((1, 3, self.pic.num_channels), 2, dtype=np.uint8),
        'read3':
            None,
        'read4':
            np.full((1, 3, self.pic.num_channels), 3, dtype=np.uint8),
        'read1_parent2':
            np.full((1, 3, self.pic.num_channels), 1, dtype=np.uint8),
        'read2_parent2':
            np.full((1, 3, self.pic.num_channels), 2, dtype=np.uint8),
        'read3_parent2':
            None,
        'read4_parent2':
            np.full((1, 3, self.pic.num_channels), 3, dtype=np.uint8),
    }

    # Setup our shared mocks.
    mock_encoder = mock.Mock(spec=['encode_read', 'encode_reference'])
    mock_encoder.encode_reference.return_value = self.expected_rows['ref']

    # pylint: disable=unused-argument
    def get_read_row(dv_call, refbases, read, pos, alt_allele):
      return self.expected_rows[read.fragment_name]

    mock_encoder.encode_read.side_effect = get_read_row

    self.mock_enc_ref = mock_encoder.encode_reference
    self.mock_enc_read = mock_encoder.encode_read

    self.pic._encoder = mock_encoder

  def assertImageMatches(self, actual_image, *row_names):
    """Checks that actual_image matches an image from constructed row_names."""
    expected_image = np.vstack([self.expected_rows[name] for name in row_names])
    self.assertEqual(actual_image.shape, expected_image.shape)
    npt.assert_equal(actual_image, expected_image)

  def test_image_no_reads(self):
    # This image is created just from reference and no reads. Checks that the
    # function is listening to all of our image creation parameters (e.g.,
    # reference_band_height, width, height, etc) and is filling the image with
    # empty rows when it runs out of reads.
    image = self.pic.build_pileup(self.dv_call, self.ref, [], {self.alt_allele},
                                  [], [])
    test_utils.assert_not_called_workaround(self.mock_enc_read)
    self.assertImageMatches(image, 'ref', 'ref', 'empty', 'empty', 'ref', 'ref',
                            'empty', 'empty', 'ref', 'ref', 'empty', 'empty')

  def test_image_no_reads_for_one_parent(self):
    # This image is created just from reference and no reads. Checks that the
    # function is listening to all of our image creation parameters (e.g.,
    # reference_band_height, width, height, etc) and is filling the image with
    # empty rows when it runs out of reads.
    image = self.pic.build_pileup(self.dv_call, self.ref,
                                  [self.read1, self.read2], {self.alt_allele},
                                  [self.read1_parent1, self.read2_parent1], [])
    self.assertImageMatches(image, 'ref', 'ref', 'read1_parent1',
                            'read2_parent1', 'ref', 'ref', 'read1', 'read2',
                            'ref', 'ref', 'empty', 'empty')

  def test_image_one_read(self):
    # We add a single read to our image.
    image = self.pic.build_pileup(self.dv_call, self.ref, [self.read1],
                                  {self.alt_allele}, [self.read1_parent1],
                                  [self.read1_parent2])
    self.assertImageMatches(image, 'ref', 'ref', 'read1_parent1', 'empty',
                            'ref', 'ref', 'read1', 'empty', 'ref', 'ref',
                            'read1_parent2', 'empty')

  def test_image_creation_with_more_reads_than_rows(self):
    # Read1 should be dropped because there's only space for Read2 and Read4.
    # If there are more reads than rows, a deterministic random subset is used.
    image = self.pic.build_pileup(
        self.dv_call, self.ref, [self.read1, self.read2, self.read4],
        {self.alt_allele},
        [self.read1_parent1, self.read2_parent1, self.read4_parent1],
        [self.read1_parent2, self.read2_parent2, self.read4_parent2])
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read1_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent2, 9,
                  {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read2_parent1',
                            'read4_parent1', 'ref', 'ref', 'read2', 'read4',
                            'ref', 'ref', 'read2_parent2', 'read4_parent2')

  def test_image_creation_with_bad_read(self):
    # Read 3 is bad (return value is None) so it should be skipped.
    image = self.pic.build_pileup(
        self.dv_call, self.ref, [self.read1, self.read3, self.read2],
        {self.alt_allele},
        [self.read1_parent1, self.read3_parent1, self.read2_parent1],
        [self.read1_parent2, self.read3_parent2, self.read2_parent2])
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read1_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent2, 9,
                  {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read1_parent1',
                            'read2_parent1', 'ref', 'ref', 'read1', 'read2',
                            'ref', 'ref', 'read1_parent2', 'read2_parent2')

  def test_image_creation_with_all_reads_in_new_order(self):
    # Read 3 is bad (return value is None) so it should be skipped. Read2 should
    # also be dropped because there's only space for Read1 and Read4. If there
    # are more reads than rows, a deterministic random subset is used.
    image = self.pic.build_pileup(
        self.dv_call, self.ref,
        [self.read2, self.read3, self.read4, self.read1], {self.alt_allele}, [
            self.read2_parent1, self.read3_parent1, self.read4_parent1,
            self.read1_parent1
        ], [
            self.read2_parent2, self.read3_parent2, self.read4_parent2,
            self.read1_parent2
        ])
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read2_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read3_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1_parent2, 9,
                  {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read1_parent1',
                            'read4_parent1', 'ref', 'ref', 'read1', 'read4',
                            'ref', 'ref', 'read1_parent2', 'read4_parent2')

  def test_image_different_heights(self):
    # Parent and child image heights differ.
    # Read1 should be dropped because there's only space for Read2 and Read4.
    # If there are more reads than rows, a deterministic random subset is used.
    # For parents, Read4 will also be dropped.
    self.custom_pic = _make_image_creator(
        None,
        None,
        width=3,
        height_parent=3,
        height_child=4,
        reference_band_height=2,
        sequencing_type=deepvariant_pb2.PileupImageOptions.TRIO)
    self.custom_pic._encoder = self.pic._encoder

    image = self.custom_pic.build_pileup(
        self.dv_call, self.ref, [self.read1, self.read2, self.read4],
        {self.alt_allele},
        [self.read1_parent1, self.read2_parent1, self.read4_parent1],
        [self.read1_parent2, self.read2_parent2, self.read4_parent2])
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.mock_enc_ref.assert_called_with(self.ref)
    self.assertEqual(self.mock_enc_read.call_args_list, [
        mock.call(self.dv_call, self.ref, self.read1_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent1, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4, 9, {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read1_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read2_parent2, 9,
                  {self.alt_allele}),
        mock.call(self.dv_call, self.ref, self.read4_parent2, 9,
                  {self.alt_allele}),
    ])
    self.assertImageMatches(image, 'ref', 'ref', 'read2_parent1', 'ref', 'ref',
                            'read2', 'read4', 'ref', 'ref', 'read2_parent2')


class PileupImageCreatorTest(parameterized.TestCase):

  def setUp(self):
    super(PileupImageCreatorTest, self).setUp()
    self.options = pileup_image.default_options()
    self.options.width = 5
    self.mock_ref_reader = mock.MagicMock(spec=fasta.IndexedFastaReader)
    self.mock_ref_reader.query.return_value = 'ACGT'
    self.mock_ref_reader.is_valid.return_value = True
    self.mock_sam_reader = mock.MagicMock()
    self.mock_sam_reader.query.return_value = ['read1', 'read2']
    self.mock_sam_reader_parent1 = mock.MagicMock()
    self.mock_sam_reader_parent1.query.return_value = [
        'read1_parent1', 'read2_parent1'
    ]
    self.mock_sam_reader_parent2 = mock.MagicMock()
    self.mock_sam_reader_parent2.query.return_value = [
        'read1_parent2', 'read2_parent2'
    ]
    self.dv_call = _make_dv_call()
    self.variant = self.dv_call.variant
    self.pic = self._make_pic()

  def _make_pic(self, **kwargs):
    return pileup_image.PileupImageCreator(self.options, self.mock_ref_reader,
                                           self.mock_sam_reader,
                                           self.mock_sam_reader_parent1,
                                           self.mock_sam_reader_parent2,
                                           **kwargs)

  @parameterized.parameters(
      ('A', ['C'], [['C']]),
      ('A', ['C', 'G'], [['C'], ['G'], ['C', 'G']]),
  )
  def test_alt_combinations(self, ref, alts, expected):
    variant = variants_pb2.Variant(reference_bases=ref, alternate_bases=alts)
    self.assertEqual(expected, list(self.pic._alt_allele_combinations(variant)))

  @parameterized.parameters(
      ('A', ['C'], [['C']]),
      ('A', ['C', 'G'], [['C'], ['G']]),
  )
  def test_alt_combinations_no_het_alt(self, ref, alts, expected):
    options = pileup_image.default_options()
    options.multi_allelic_mode = (
        deepvariant_pb2.PileupImageOptions.NO_HET_ALT_IMAGES)
    pic = pileup_image.PileupImageCreator(options, self.mock_ref_reader,
                                          self.mock_sam_reader)
    variant = variants_pb2.Variant(reference_bases=ref, alternate_bases=alts)
    self.assertEqual(expected, list(pic._alt_allele_combinations(variant)))

  def test_get_reference_bases_good_region(self):
    self.dv_call.variant.start = 10
    region = ranges.make_range(self.variant.reference_name, 8, 13)

    actual = self.pic.get_reference_bases(self.variant)
    self.assertEqual('ACGT', actual)
    self.mock_ref_reader.is_valid.assert_called_once_with(region)
    self.mock_ref_reader.query.assert_called_once_with(region)

  def test_get_reference_bases_bad_region_returns_none(self):
    self.mock_ref_reader.is_valid.return_value = False
    self.dv_call.variant.start = 3

    self.assertIsNone(self.pic.get_reference_bases(self.variant))
    test_utils.assert_called_once_workaround(self.mock_ref_reader.is_valid)
    self.mock_ref_reader.query.assert_not_called()

  def test_create_pileup_image_returns_none_for_bad_region(self):
    self.mock_ref_reader.is_valid.return_value = False
    self.dv_call.variant.start = 3
    self.assertIsNone(self.pic.create_pileup_images(self.dv_call))
    test_utils.assert_called_once_workaround(self.mock_ref_reader.is_valid)
    self.mock_ref_reader.query.assert_not_called()

  def test_create_pileup_image(self):
    self.dv_call.variant.alternate_bases[:] = ['C', 'T']

    with mock.patch.object(
        self.pic, 'build_pileup', autospec=True) as mock_encoder:
      mock_encoder.side_effect = ['mi1', 'mi2', 'mi3']

      self.assertEqual([
          (['C'], 'mi1'),
          (['T'], 'mi2'),
          (['C', 'T'], 'mi3'),
      ], self.pic.create_pileup_images(self.dv_call))

      def _expected_call(alts):
        return mock.call(
            dv_call=self.dv_call,
            refbases=self.mock_ref_reader.query.return_value,
            reads=self.mock_sam_reader.query.return_value,
            alt_alleles=alts,
            reads_parent1=self.mock_sam_reader_parent1.query.return_value,
            reads_parent2=self.mock_sam_reader_parent2.query.return_value)

      self.assertEqual(mock_encoder.call_count, 3)
      mock_encoder.assert_has_calls([
          _expected_call(['C']),
          _expected_call(['T']),
          _expected_call(['C', 'T']),
      ])

  def test_create_pileup_images_with_alt_align(self):
    self.dv_call.variant.alternate_bases[:] = ['C', 'T']
    haplotype_sequences = {'C': 'seq for C', 'T': 'seq for T'}
    haplotype_alignments = {'C': 'reads for C', 'T': 'reads for T'}
    parent1_hap_alns = {'C': 'parent1 reads for C', 'T': 'parent1 reads for T'}
    parent2_hap_alns = {'C': 'parent2 reads for C', 'T': 'parent2 reads for T'}

    with mock.patch.object(
        self.pic, 'build_pileup', autospec=True) as mock_encoder:
      # The represent_alt_aligned_pileups function checks for shape of the
      # arrays, so mock with actual numpy arrays here.
      arr = np.zeros((100, 221, 6))
      final_pileup = np.zeros((300, 221, 6))
      mock_encoder.side_effect = [arr] * 9
      self.pic._options.alt_aligned_pileup = 'rows'

      output = self.pic.create_pileup_images(
          self.dv_call,
          haplotype_alignments=haplotype_alignments,
          haplotype_sequences=haplotype_sequences,
          parent1_hap_alns=parent1_hap_alns,
          parent2_hap_alns=parent2_hap_alns)
      expected_output = [(['C'], final_pileup), (['T'], final_pileup),
                         (['C', 'T'], final_pileup)]
      self.assertEqual([x[0] for x in output], [x[0] for x in expected_output])
      self.assertEqual([x[1].shape for x in output],
                       [x[1].shape for x in expected_output])

      def _expected_ref_based_call(alts):
        return mock.call(
            dv_call=self.dv_call,
            refbases=self.mock_ref_reader.query.return_value,
            reads=self.mock_sam_reader.query.return_value,
            alt_alleles=alts,
            reads_parent1=self.mock_sam_reader_parent1.query.return_value,
            reads_parent2=self.mock_sam_reader_parent2.query.return_value)

      def _expected_alt_based_call(alts, refbases, reads):
        return mock.call(
            dv_call=self.dv_call,
            refbases=refbases,
            reads=reads,
            alt_alleles=alts,
            custom_ref=True,
            reads_parent1='parent1 ' + reads,
            reads_parent2='parent2 ' + reads)

      self.assertEqual(mock_encoder.call_count, 7)
      mock_encoder.assert_has_calls(
          [
              # Pileup for 'C':
              _expected_ref_based_call(['C']),
              _expected_alt_based_call(['C'], 'seq for C', 'reads for C'),
              # Pileup for 'T':
              _expected_ref_based_call(['T']),
              _expected_alt_based_call(['T'], 'seq for T', 'reads for T'),
              # Pileup for 'C/T':
              _expected_ref_based_call(['C', 'T']),
              _expected_alt_based_call(['C', 'T'], 'seq for C', 'reads for C'),
              _expected_alt_based_call(['C', 'T'], 'seq for T', 'reads for T'),
          ],
          any_order=True)

  @parameterized.parameters(
      ((100, 221, 6), 'rows', (300, 221, 6)),
      ((100, 221, 6), 'base_channels', (100, 221, 8)),
      ((100, 221, 6), 'diff_channels', (100, 221, 8)),
  )
  def test_represent_alt_aligned_pileups_outputs_correct_shape(
      self, input_shape, representation, expected_output_shape):

    ref_image = np.zeros(input_shape)
    alt_image1 = np.zeros(input_shape)
    alt_image2 = np.zeros(input_shape)

    # Test with one alt image.
    output = pileup_image._represent_alt_aligned_pileups(
        representation, ref_image, [alt_image1])
    self.assertEqual(output.shape, expected_output_shape)

    # Test with two alt images.
    output = pileup_image._represent_alt_aligned_pileups(
        representation, ref_image, [alt_image1, alt_image2])
    self.assertEqual(output.shape, expected_output_shape)

  def test_represent_alt_aligned_pileups_raises_on_invalid_representation(self):
    # Representation must be one of the valid options.
    ref_image = np.zeros((100, 221, 6))
    alt_image = np.zeros((100, 221, 6))
    with self.assertRaises(ValueError):
      pileup_image._represent_alt_aligned_pileups('invalid', ref_image,
                                                  [alt_image])

  def test_represent_alt_aligned_pileups_raises_on_different_shapes(self):
    # Different shapes of input images should raise error.
    ref_image = np.zeros((100, 221, 6))
    alt_image = np.zeros((500, 221, 6))
    with self.assertRaises(ValueError):
      pileup_image._represent_alt_aligned_pileups('rows', ref_image,
                                                  [alt_image])

  def test_represent_alt_aligned_pileups_raises_on_too_many_alt_images(self):
    # Different shapes of input images should raise error.
    ref_image = np.zeros((100, 221, 6))
    alt_image = np.zeros((100, 221, 6))
    with self.assertRaises(ValueError):
      pileup_image._represent_alt_aligned_pileups(
          'rows', ref_image, [alt_image, alt_image, alt_image])


if __name__ == '__main__':
  absltest.main()