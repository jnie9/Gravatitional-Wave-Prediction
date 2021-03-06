"""
Train TWO Deep Neural Network to predict mass and spin of two gravitational waves.
train signal: 8190 x 8192
test signal: 910 x 8192
"""

import tensorflow as tf
import deepGW_4_4
import numpy as np 
import time
import pickle
import scipy.io as sio
import matplotlib.pyplot as plt
plt.switch_backend('agg')

"""
<<<Hyperparameters>>>
"""
all_num_gpus = [1]
all_num_steps = [15000]      # total number of steps to train (500 signals per step)
all_params = ['mass', 'spin']
lr = 0.0001 			#not sure whether this matters 
SNR_max = 16
SNR_min = 0.5
SNR_drop_step = 1000    # SNR remain at SNR_max until drop_step
train_step_size = 50
#num_epoch = 300
log_device_placement = False    # toggle to true to print log


def tower_loss(scope, inputs, labels):

    inputs = deepGW_4.convert_to_tensor_float(inputs)
    labels = deepGW_4.convert_to_tensor_float(labels)

    """
    pred, logits = deepGW_4.inference_mass_predictor(inputs)

    _ = deepGW_4.loss(logits, labels)

    _ = deepGW_4.accuracy(pred, labels)
    """

    pred = deepGW_4.inference_mass_estimator_4conv(inputs)
    _ = deepGW_4.loss_estimator(pred, labels)
    _ = deepGW_4.accuracy_estimator(pred, labels)

    losses = tf.get_collection('losses', scope)
    accuracies = tf.get_collection('accuracies', scope)
    total_loss = tf.add_n(losses, name='total_loss')
    total_accuracy = tf.add_n(accuracies, name='total_accuracy')

    return total_loss, total_accuracy


def average_gradients(tower_grads):
    average_grads = []
    for grad_and_vars in zip(*tower_grads):

        grads = []
        for g, _ in grad_and_vars:
            expanded_g = tf.expand_dims(g, 0)
            grads.append(expanded_g)

        grad = tf.concat(axis=0, values=grads)
        grad = tf.reduce_mean(grad, 0)

        v = grad_and_vars[0][1]
        grad_and_var = (grad, v)
        average_grads.append(grad_and_var)
    return average_grads


def calc_snr(num_step):
    """
    Calculate SNR as a function of total steps, SNR remains at SNR_max for SNR_drop_step steps and then
    drops from SNR_max to SNR_min
    :param num_step(int): total steps
    :return SNR(numpy array): list of all SNRs per step (num_step,)
    """
    x = np.arange(num_step)
    SNRs = (SNR_max - SNR_min) / (num_step - SNR_drop_step) * (-x + num_step)
    SNRs[:SNR_drop_step] = SNR_max
    return SNRs


def train(inputs, labels, num_gpus, num_step, param):

    with tf.device('/cpu:0'):
        tf.reset_default_graph()
        global_step = tf.Variable(0, name='global_step', trainable=False)
        opt = tf.train.AdamOptimizer(lr)

        with tf.name_scope('Input'):
            X = tf.placeholder(tf.float32, [None, num_gpus, 8192])
        with tf.name_scope('Label'):
            Y_ = tf.placeholder(tf.float32, [None, num_gpus, 2])

        tower_grads = []
        with tf.variable_scope(tf.get_variable_scope()):
            for i in range(num_gpus):
                with tf.device('/gpu:%d' % i):
                    with tf.name_scope('tower_%d' % i) as scope:
                        loss, accuracy = tower_loss(scope, X[:, i, :], Y_[:, i, :])
                        tf.get_variable_scope().reuse_variables()
                        grads = opt.compute_gradients(loss)
                        tower_grads.append(grads)

        grads = average_gradients(tower_grads)
        apply_gradient_op = opt.apply_gradients(grads, global_step=global_step)

        init = tf.global_variables_initializer()
        sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=log_device_placement))
        sess.run(init)
        tf.train.start_queue_runners(sess=sess)

        # 	inputs, labels = deepGW_4.generate_batch_input(data=inputs, phase='train', snr=snr, size=2*len(inputs), num_epoch, epoch)

        # 	inputs, labels = deepGW_4.generate_batch_input_estimator(inputs, labels, 'train', snr, len(inputs), num_epoch, epoch)
        # 	num_step = inputs.shape[0] // (train_step_size * num_gpus)
        # 	input_epoch, label_epoch = deepGW_4.prepare_data(inputs, labels)
        SNRs = calc_snr(num_step)
        all_loss, all_acc = [], []
        train_start_time = time.time()

        for step in range(num_step):
            snr = SNRs[step]
            input_epoch, label_epoch = deepGW_4.generate_batch_input_estimator(inputs, labels, 'train', snr,
                                                                             num_gpus*train_step_size, 0, 0)
            input_batch, label_batch = deepGW_4.get_a_batch(input_epoch, label_epoch, train_step_size, num_gpus, 0)

            start_time = time.time()
            _, loss_value, acc_value = sess.run([apply_gradient_op, loss, accuracy],
                                                feed_dict={X: input_batch, Y_: label_batch})
            duration = time.time() - start_time
            all_loss.append(loss_value)     # loss: MSE
            all_acc.append(acc_value)       # acc: relatively error

            if step % 10 == 0:
                num_examples_per_step = train_step_size * num_gpus
                examples_per_sec = num_examples_per_step / duration
                sec_per_batch = duration / num_gpus

                format_str = ('step %d, mse = %.5f, relative_error = %.2f (%.1f examples/sec; %.3f sec/batch)')
                print(format_str % (step, loss_value, acc_value, examples_per_sec, sec_per_batch))

        # save model for use in testing/prediction process
        saver = tf.train.Saver()
        model_path = "/home/abc99lr/Gravatitional-Wave-Prediction/mass_small_4_param/Model/Model_" + param + str(num_gpus) + "_GPU.ckpt"
        #model_path = "/home/nie9/Gravatitional-Wave-Prediction/mass_small_4_param/Model/Model_" + param + str(num_gpus) + "_GPU.ckpt"
        saver.save(sess, model_path)
        #sess.close()

        total_time = int(time.time() - train_start_time)
        print("Trained {} on {} gpus in {} steps in {} hr {} min".format(param, num_gpus, num_step, total_time // 3600,
                                                                        (total_time % 3600) // 60))


    # inputs, labels = deepGW_4.read_dataset(phase='val')
    # test_loss = []
    # test_acc = []
    # test_snr = np.linspace(0.2, 3, 29)

    # for i in range(29):
    # 	print("SNR = ", test_snr[i])

    # 	testsig, testlabel = deepGW_4.generate_batch_input_estimator(inputs, labels, 'test', snr, 1000, 0, 0)

    # 	m, r = sess.run([loss, accuracy], feed_dict={X: testsig, Y_: testlabel})

    # 	print('test:' + ' mse:' + str(m) + ' relative_error:' + str(r))

    # test_loss.append(m)
    # test_acc.append(r)

    # sio.savemat('/home/ruilan2/multi_gpu/loss.mat', {'mse': test_loss})
    # sio.savemat('/home/ruilan2/multi_gpu/acc.mat', {'ree': test_acc})

    return all_loss, all_acc


"""
def test(inputs, labels):

    test_loss = []
    test_acc = []
    test_snr = np.linspace(0.2, 3, 29)

    for i in range(29):
        print("SNR = ", test_snr[i])

        testsig, testlabel = deepGW_4.generate_batch_input_estimator(inputs, labels, 'test', snr, 1000, 0, 0)

        m, r = sess.run([loss, accuracy], feed_dict={X: testsig, Y_: testlabel})

        print('test:' + ' mse:' + str(m) + ' relative_error:' + str(r))

    test_loss.append(m)
    test_acc.append(r)

    sio.savemat('/home/ruilan2/multi_gpu/ver3/loss.mat', {'mse': test_loss})
    sio.savemat('/home/ruilan2/multi_gpu/ver3/acc.mat', {'ree': test_acc})
    pass
"""


def make_plot(loss, acc, param):
    """
    Train step: plot step vs. MSE, vs. realative_error, vs. SNR
    :param loss(list): list of MSEs
    :param acc(list): list of relative error
    :return: None
    """
    #counter = 1
    for i in range(len(all_num_gpus)):
        num_gpu = str(all_num_gpus[i])
        fig = plt.figure()
        steps = np.arange(0, all_num_steps[i], 1)
        SNRs = calc_snr(all_num_steps[i])
        ax1 = fig.add_subplot(311)
        ax1.plot(steps, SNRs)
        plt.ylabel("SNR")
        ax2 = fig.add_subplot(312)
        ax2.plot(steps, loss[i])
        plt.ylabel("MSE")
        ax3 = fig.add_subplot(313)
        ax3.plot(steps, acc[i])
        plt.xlabel("Step")
        plt.ylabel("Relative Error (%)")
        xticklabels = ax1.get_xticklabels() + ax2.get_xticklabels()
        plt.setp(xticklabels, visible=False)
        plt.suptitle("Trained {} on {} GPUs in {} steps".format(param, num_gpu, all_num_steps[i]))
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        plt.savefig("result_img_4_param/Train_" + param + "_" + num_gpu + "_GPUs")
        #plt.savefig("result_img/Train_" + str(counter) + "_GPUs")
        #counter += 1
        sio.savemat("/home/abc99lr/Gravatitional-Wave-Prediction/mass_small_4_param/mat_4_param/train_loss_" + str(i) + "_" + num_gpu + "_gpu.mat", {'cross_entropy': loss[i]})
        sio.savemat("/home/abc99lr/Gravatitional-Wave-Prediction/mass_small_4_param/mat_4_param/train_acc_" + str(i) + "_" + num_gpu + "_gpu.mat", {'accuracy': acc[i]})



if __name__ == "__main__":
    inputs, labels = deepGW_4.read_dataset_4paras(phase='train')    # input shape = (9180, 8192)
    print("")

    '''
    loss, acc = [], []
    for p in range(len(all_params)):
        for g in range(len(all_num_gpus)):
            ret_value = train(inputs, labels[p], all_num_gpus[g], all_num_steps[g], all_params[p])
            loss.append(ret_value[0])
            acc.append(ret_value[1])
        make_plot(loss, acc, all_params[p])
    '''



#inputs, labels = deepGW_4.read_dataset(phase='val')
#test(inputs, labels)
