# A Neural Network Architecture Combining Gated Recurrent Unit (GRU) and
# Support Vector Machine (SVM) for Intrusion Detection in Network Traffic Data
# Copyright (C) 2017  Abien Fred Agarap
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# ==============================================================================

"""Implementation of SVM for Intrusion Detection"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

__version__ = '0.3.2'
__author__ = 'Abien Fred Agarap'

import argparse
import data
import os
import sys
import tensorflow as tf
import time

# Hyper-parameters
BATCH_SIZE = 256
HM_EPOCHS = 1
LEARNING_RATE = 1e-5
N_CLASSES = 2
SEQUENCE_LENGTH = 21
SVM_C = 1


class Svm:

    def __init__(self, checkpoint_path, log_path, model_name):
        self.checkpoint_path = checkpoint_path
        self.log_path = log_path
        self.model_name = model_name

        def __graph__():
            """Building the inference graph"""
            learning_rate = tf.placeholder(dtype=tf.float32, name='learning_rate')

            with tf.name_scope('input'):
                # [BATCH_SIZE, SEQUENCE_LENGTH]
                x_input = tf.placeholder(dtype=tf.float32, shape=[None, SEQUENCE_LENGTH], name='x_input')

                # [BATCH_SIZE, N_CLASSES]
                y_input = tf.placeholder(dtype=tf.uint8, shape=[None], name='y_input')

                y_onehot = tf.one_hot(y_input, 2, on_value=1, off_value=-1, name='y_onehot')

            with tf.name_scope('training_ops'):
                with tf.name_scope('weights'):
                    weight = tf.get_variable(name='weights',
                                             initializer=tf.random_normal([SEQUENCE_LENGTH, N_CLASSES], stddev=0.01))
                    self.variable_summaries(weight)
                with tf.name_scope('biases'):
                    bias = tf.get_variable(name='biases', initializer=tf.constant(0.1, shape=[N_CLASSES]))
                    self.variable_summaries(bias)
                with tf.name_scope('Wx_plus_b'):
                    y_hat = tf.matmul(x_input, weight) + bias
                    tf.summary.histogram('pre-activations', y_hat)

            # L2-SVM
            with tf.name_scope('svm'):
                regularization = 0.5 * tf.reduce_sum(tf.square(weight))
                hinge_loss = tf.reduce_sum(
                    tf.square(tf.maximum(tf.zeros([BATCH_SIZE, N_CLASSES]), 1 - tf.cast(y_onehot, tf.float32) * y_hat)))
                with tf.name_scope('loss'):
                    loss = regularization + SVM_C * hinge_loss
            tf.summary.scalar('loss', loss)

            optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(loss)

            with tf.name_scope('accuracy'):
                predicted_class = tf.sign(y_hat)
                predicted_class = tf.identity(predicted_class, name='prediction')
                with tf.name_scope('correct_prediction'):
                    correct = tf.equal(tf.argmax(predicted_class, 1), tf.argmax(y_onehot, 1))
                with tf.name_scope('accuracy'):
                    accuracy = tf.reduce_mean(tf.cast(correct, 'float'))
            tf.summary.scalar('accuracy', accuracy)

            # merge all the summaries in the inference graph
            merged = tf.summary.merge_all()

            self.x_input = x_input
            self.y_input = y_input
            self.y_onehot = y_onehot
            self.loss = loss
            self.optimizer = optimizer
            self.learning_rate = learning_rate
            self.accuracy = accuracy
            self.merged = merged

        sys.stdout.write('\n<log> Building Graph...')
        __graph__()
        sys.stdout.write('</log>\n')

    def train(self, train_data, train_size, validation_data, validation_size):
        """Train the model"""

        if not os.path.exists(self.checkpoint_path):
            os.mkdir(self.checkpoint_path)

        saver = tf.train.Saver(max_to_keep=1000)

        # variable initializer
        init_op = tf.group(tf.local_variables_initializer(), tf.global_variables_initializer())

        # get the time tuple, and parse to str
        timestamp = str(time.asctime())

        # event file to contain TF graph summaries during training
        train_writer = tf.summary.FileWriter(self.log_path + timestamp + '-training', graph=tf.get_default_graph())

        # event file to contain TF graph summaries during validation
        validation_writer = tf.summary.FileWriter(self.log_path + timestamp + '-validation', graph=tf.get_default_graph())

        with tf.Session() as sess:

            sess.run(init_op)

            checkpoint = tf.train.get_checkpoint_state(self.checkpoint_path)

            # check if a trained model exists
            if checkpoint and checkpoint.model_checkpoint_path:
                # load the graph from the trained model
                saver = tf.train.import_meta_graph(checkpoint.model_checkpoint_path + '.meta')
                # restore the variables
                saver.restore(sess, tf.train.latest_checkpoint(self.checkpoint_path))

            try:
                for step in range(HM_EPOCHS * train_size // BATCH_SIZE):
                    offset = (step * BATCH_SIZE) % train_size
                    train_feature_batch = train_data[0][offset:(offset+BATCH_SIZE)]
                    train_label_batch = train_data[1][offset:(offset+BATCH_SIZE)]

                    # dictionary for key-value pair input for training
                    feed_dict = {self.x_input: train_feature_batch, self.y_input: train_label_batch,
                                 self.learning_rate: LEARNING_RATE}

                    summary, _, epoch_loss = sess.run([self.merged, self.optimizer, self.loss], feed_dict=feed_dict)

                    # display training accuracy and loss every 100 steps and at step 0
                    if step % 100 == 0:
                        accuracy_ = sess.run(self.accuracy, feed_dict=feed_dict)
                        print('step [{}] train -- loss : {}, accuracy : {}'.format(step, epoch_loss, accuracy_))
                        train_writer.add_summary(summary, step)
                        saver.save(sess, self.checkpoint_path + self.model_name, global_step=step)
                for step in range(HM_EPOCHS * validation_size // BATCH_SIZE):

                    # display validation accuracy and loss every 100 steps
                    if step % 100 == 0 and step > 0:
                        offset = (step * BATCH_SIZE) % validation_size
                        validation_feature_batch = validation_data[0][offset:(offset + BATCH_SIZE)]
                        validation_label_batch = validation_data[1][offset:(offset + BATCH_SIZE)]

                        # dictionary for key-value pair input for validation
                        feed_dict = {self.x_input: validation_feature_batch, self.y_input: validation_label_batch}

                        summary, test_loss, test_accuracy = sess.run([self.merged, self.loss, self.accuracy],
                                                                     feed_dict=feed_dict)

                        print('step [{}] validation -- loss : {}, accuracy : {}'.format(step, test_loss, test_accuracy))
                        validation_writer.add_summary(summary, step)

            except KeyboardInterrupt:
                print('Training interrupted at {}'.format(step))
            finally:
                print('EOF -- training done at step {}'.format(step))

            saver.save(sess, self.checkpoint_path + self.model_name, global_step=step)

    @staticmethod
    def variable_summaries(var):
        with tf.name_scope('summaries'):
            mean = tf.reduce_mean(var)
            tf.summary.scalar('mean', mean)
            with tf.name_scope('stddev'):
                stddev = tf.sqrt(tf.reduce_mean(tf.square(var - mean)))
            tf.summary.scalar('stddev', stddev)
            tf.summary.scalar('max', tf.reduce_max(var))
            tf.summary.scalar('min', tf.reduce_min(var))
            tf.summary.histogram('histogram', var)


def parse_args():
    parser = argparse.ArgumentParser(description='SVM for Intrusion Detection')
    group = parser.add_argument_group('Arguments')
    group.add_argument('-t', '--train_dataset', required=True, type=str,
                       help='the NumPy array training dataset (*.npy) to be used')
    group.add_argument('-v', '--validation_dataset', required=True, type=str,
                       help='the NumPy array validation dataset (*.npy) to be used')
    group.add_argument('-c', '--checkpoint_path', required=True, type=str,
                       help='path where to save the trained model')
    group.add_argument('-l', '--log_path', required=True, type=str,
                       help='path where to save the TensorBoard logs')
    group.add_argument('-m', '--model_name', required=True, type=str,
                       help='filename for the trained model')
    arguments = parser.parse_args()
    return arguments


def main(arguments):

    train_features, train_labels = data.load_data(dataset=arguments.train_dataset)
    validation_features, validation_labels = data.load_data(dataset=arguments.validation_dataset)

    train_size = train_features.shape[0]
    validation_size = validation_features.shape[0]

    model = Svm(checkpoint_path=arguments.checkpoint_path, log_path=arguments.log_path, model_name=arguments.model_name)

    model.train(train_data=[train_features, train_labels], train_size=train_size,
                validation_data=[validation_features, validation_labels], validation_size=validation_size)


if __name__ == '__main__':
    args = parse_args()

    main(args)