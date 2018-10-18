# Copyright 2018, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for serialization.py."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Dependency imports
import numpy as np
import tensorflow as tf

from tensorflow_federated.python.core.api import types

from tensorflow_federated.python.core.impl import serialization


class SerializationTest(tf.test.TestCase):

  def test_serialize_type_with_tensor_dtype_without_shape(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type(tf.int32)),
        'tensor { dtype: DT_INT32 shape { } }')

  def test_serialize_type_with_tensor_dtype_with_shape(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type((tf.int32, [10, 20]))),
        'tensor { dtype: DT_INT32 '
        'shape { dim { size: 10 } dim { size: 20 } } }')

  def test_serialize_type_with_tensor_dtype_with_shape_undefined_dim(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type((tf.int32, [None]))),
        'tensor { dtype: DT_INT32 '
        'shape { dim { size: -1 } } }')

  def test_serialize_type_with_string_sequence(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type(
            types.SequenceType(tf.string))),
        'sequence { element { tensor { dtype: DT_STRING shape { } } } }')

  def test_serialize_type_with_tensor_tuple(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type(
            [('x', tf.int32), ('y', tf.string), tf.float32, ('z', tf.bool)])),
        'tuple { '
        'element { name: "x" value { tensor { dtype: DT_INT32 shape { } } } } '
        'element { name: "y" value { tensor { dtype: DT_STRING shape { } } } } '
        'element { value { tensor { dtype: DT_FLOAT shape { } } } } '
        'element { name: "z" value { tensor { dtype: DT_BOOL shape { } } } } }')

  def test_serialize_type_with_nested_tuple(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type(
            [('x', [('y', [('z', tf.bool)])])])),
        'tuple { element { name: "x" value { '
        'tuple { element { name: "y" value { '
        'tuple { element { name: "z" value { '
        'tensor { dtype: DT_BOOL shape { } } '
        '} } } } } } } } }')

  def test_serialize_type_with_function(self):
    self.assertEqual(
        _compact_repr(serialization.serialize_type(
            types.FunctionType((tf.int32, tf.int32), tf.bool))),
        'function { parameter { tuple { '
        'element { value { tensor { dtype: DT_INT32 shape { } } } } '
        'element { value { tensor { dtype: DT_INT32 shape { } } } } '
        '} } result { tensor { dtype: DT_BOOL shape { } } } }')

  def test_serialize_deserialize_tensor_types(self):
    self._serialize_deserialize_roundtrip_test([
        tf.int32,
        (tf.int32, [10]),
        (tf.int32, [None])])

  def test_serialize_deserialize_sequence_types(self):
    self._serialize_deserialize_roundtrip_test([
        types.SequenceType(tf.int32),
        types.SequenceType([tf.int32, tf.bool]),
        types.SequenceType([tf.int32, types.SequenceType(tf.bool)])])

  def test_serialize_deserialize_named_tuple_types(self):
    self._serialize_deserialize_roundtrip_test([
        (tf.int32, tf.bool),
        (tf.int32, ('x', tf.bool)),
        ('x', tf.int32)])

  def test_serialize_deserialize_function_types(self):
    self._serialize_deserialize_roundtrip_test([
        types.FunctionType(tf.int32, tf.bool),
        types.FunctionType(None, tf.bool)])

  def _serialize_deserialize_roundtrip_test(self, type_list):
    """Performs roundtrip serialization/deserialization of the given types.

    Args:
      type_list: A list of instances of types.Type or things convertible to it.
    """
    for t in type_list:
      t1 = types.to_type(t)
      p1 = serialization.serialize_type(t1)
      t2 = serialization.deserialize_type(p1)
      p2 = serialization.serialize_type(t2)
      self.assertEqual(repr(t1), repr(t2))
      self.assertEqual(repr(p1), repr(p2))
      self.assertTrue(t1.is_assignable_from(t2))
      self.assertTrue(t2.is_assignable_from(t1))

  def test_serialize_tensorflow_with_no_parameter(self):
    comp = serialization.serialize_py_func_as_tf_computation(
        lambda: tf.constant(99))
    self.assertEqual(
        str(serialization.deserialize_type(comp.type)), '( -> int32)')
    self.assertEqual(comp.WhichOneof('computation'), 'tensorflow')
    results = tf.Session().run(tf.import_graph_def(
        comp.tensorflow.graph_def, None, [
            comp.tensorflow.result.tensor.tensor_name]))
    self.assertEqual(results, [99])

  def test_serialize_tensorflow_with_simple_add_three_lambda(self):
    comp = serialization.serialize_py_func_as_tf_computation(
        lambda x: x + 3, tf.int32)
    self.assertEqual(
        str(serialization.deserialize_type(comp.type)), '(int32 -> int32)')
    self.assertEqual(comp.WhichOneof('computation'), 'tensorflow')
    parameter = tf.constant(1000)
    results = tf.Session().run(tf.import_graph_def(
        comp.tensorflow.graph_def,
        {comp.tensorflow.parameter.tensor.tensor_name: parameter},
        [comp.tensorflow.result.tensor.tensor_name]))
    self.assertEqual(results, [1003])

  def test_serialize_tensorflow_with_data_set_sum_lambda(self):
    # TODO(b/113112885): When support for Dataset.reduce() becomes available,
    # replace with "lambda ds: ds.reduce(np.int64(0), lambda x, y: x + y)".
    def _legacy_dataset_reducer_example(ds):
      return tf.contrib.data.reduce_dataset(ds, tf.contrib.data.Reducer(
          lambda _: np.int64(0), lambda x, y: x + y, lambda x: x))
    comp = serialization.serialize_py_func_as_tf_computation(
        _legacy_dataset_reducer_example, types.SequenceType(tf.int64))
    self.assertEqual(
        str(serialization.deserialize_type(comp.type)), '(int64* -> int64)')
    self.assertEqual(comp.WhichOneof('computation'), 'tensorflow')
    parameter = tf.data.Dataset.range(5)
    results = tf.Session().run(tf.import_graph_def(
        comp.tensorflow.graph_def,
        {comp.tensorflow.parameter.sequence.iterator_string_handle_name: (
            parameter.make_one_shot_iterator().string_handle())},
        [comp.tensorflow.result.tensor.tensor_name]))
    self.assertEqual(results, [10])


def _compact_repr(m):
  """Returns a compact representation of message 'm'.

  Args:
    m: A protocol buffer message instance.

  Returns:
    A compact string representation of 'm' with all newlines replaced with
    spaces, and stringd multiple spaces replaced with just one.
  """
  s = repr(m).replace('\n', ' ')
  while '  ' in s:
    s = s.replace('  ', ' ')
  return s.strip()


if __name__ == '__main__':
  tf.test.main()
