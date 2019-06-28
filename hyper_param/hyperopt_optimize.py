
"""Auto-optimizing a neural network with Hyperopt (TPE algorithm)."""
import os

import tensorflow as tf
from gradient_sdk import model_dir

from neural_net import build_model
from utils import load_best_hyperspace, is_gpu_available, print_json

from keras.utils import plot_model
import keras.backend as K
from hyperopt import hp, tpe

import traceback

from gradient_sdk.hyper_parameter import hyper_tune

MAX_EVALS = os.environ.get('HKS_MAX_EVALS', 5)
EXPERIMENT_NAME = os.environ.get('EXPERIMENT_NAME')
PLOT_FOLDER_PATH = model_dir(EXPERIMENT_NAME)
WORKING_ENVIRONMENT = os.environ.get('HKS_ENVIRONMENT', 'paperspace')


space = {
    # This loguniform scale will multiply the learning rate, so as to make
    # it vary exponentially, in a multiplicative fashion rather than in
    # a linear fashion, to handle his exponentialy varying nature:
    'lr_rate_mult': hp.loguniform('lr_rate_mult', -0.5, 0.5),
    # L2 weight decay:
    'l2_weight_reg_mult': hp.loguniform('l2_weight_reg_mult', -1.3, 1.3),
    # Batch size fed for each gradient update
    'batch_size': hp.quniform('batch_size', 100, 450, 5),
    # Choice of optimizer:
    'optimizer': hp.choice('optimizer', ['Adam', 'Nadam', 'RMSprop']),
    # Coarse labels importance for weights updates:
    'coarse_labels_weight': hp.uniform('coarse_labels_weight', 0.1, 0.7),
    # Uniform distribution in finding appropriate dropout values, conv layers
    'conv_dropout_drop_proba': hp.uniform('conv_dropout_proba', 0.0, 0.35),
    # Uniform distribution in finding appropriate dropout values, FC layers
    'fc_dropout_drop_proba': hp.uniform('fc_dropout_proba', 0.0, 0.6),
    # Use batch normalisation at more places?
    'use_BN': hp.choice('use_BN', [False, True]),

    # Use a first convolution which is special?
    'first_conv': hp.choice(
        'first_conv', [None, hp.choice('first_conv_size', [3, 4])]
    ),
    # Use residual connections? If so, how many more to stack?
    'residual': hp.choice(
        'residual', [None, hp.quniform(
            'residual_units', 1 - 0.499, 4 + 0.499, 1)]
    ),
    # Let's multiply the "default" number of hidden units:
    'conv_hiddn_units_mult': hp.loguniform('conv_hiddn_units_mult', -0.6, 0.6),
    # Number of conv+pool layers stacked:
    'nb_conv_pool_layers': hp.choice('nb_conv_pool_layers', [2, 3]),
    # Starting conv+pool layer for residual connections:
    'conv_pool_res_start_idx': hp.quniform('conv_pool_res_start_idx', 0, 2, 1),
    # The type of pooling used at each subsampling step:
    'pooling_type': hp.choice('pooling_type', [
        'max',  # Max pooling
        'avg',  # Average pooling
        'all_conv',  # All-convolutionnal: https://arxiv.org/pdf/1412.6806.pdf
        'inception'  # Inspired from: https://arxiv.org/pdf/1602.07261.pdf
    ]),
    # The kernel_size for convolutions:
    'conv_kernel_size': hp.quniform('conv_kernel_size', 2, 4, 1),
    # The kernel_size for residual convolutions:
    'res_conv_kernel_size': hp.quniform('res_conv_kernel_size', 2, 4, 1),

    # Amount of fully-connected units after convolution feature map
    'fc_units_1_mult': hp.loguniform('fc_units_1_mult', -0.6, 0.6),
    # Use one more FC layer at output
    'one_more_fc': hp.choice(
        'one_more_fc', [None, hp.loguniform('fc_units_2_mult', -0.6, 0.6)]
    ),
    # Activations that are used everywhere
    'activation': hp.choice('activation', ['relu', 'elu'])
}


def plot(hyperspace, file_name_prefix):
    """Plot a model from it's hyperspace."""
    if PLOT_FOLDER_PATH:
        if not os.path.exists(PLOT_FOLDER_PATH):
            os.makedirs(PLOT_FOLDER_PATH)
        filename = "{}/{}.png".format(PLOT_FOLDER_PATH, file_name_prefix)
    else:
        filename = "{}.png".format(file_name_prefix)
    model = build_model(hyperspace)
    plot_model(
        model,
        to_file=filename,
        show_shapes=True
    )

    K.clear_session()
    del model


def plot_base_model():
    """Plot a basic demo model."""
    space_base_demo_to_plot = {
        'lr_rate_mult': 1.0,
        'l2_weight_reg_mult': 1.0,
        'batch_size': 300,
        'optimizer': 'Nadam',
        'coarse_labels_weight': 0.2,
        'conv_dropout_drop_proba': 0.175,
        'fc_dropout_drop_proba': 0.3,
        'use_BN': True,
        'first_conv': 4,
        'residual': 4,
        'conv_hiddn_units_mult': 1.0,
        'nb_conv_pool_layers': 3,
        'conv_pool_res_start_idx': 0.0,
        'pooling_type': 'inception',
        'conv_kernel_size': 3.0,
        'res_conv_kernel_size': 3.0,

        'fc_units_1_mult': 1.0,
        'one_more_fc': 1.0,
        'activation': 'elu'
    }
    plot(space_base_demo_to_plot, "model_demo")


def plot_best_model():
    """Plot the best model found yet."""
    space_best_model = load_best_hyperspace()
    if space_best_model is None:
        tf.logging.info("No best model to plot. Continuing...")
        return

    tf.logging.info("Best hyperspace yet:")
    print_json(space_best_model)
    plot(space_best_model, "model_best")


def run_a_trial():
    """Run one TPE meta optimisation step and save its results."""
    from optimize_cnn import optimize_cnn
    
    tf.logging.info("Attempt to resume a past training if it exists:")
    tf.logging.info("Running HyperTune...")
    tf.logging.info("Max evals: %s", MAX_EVALS)
    best = hyper_tune(
        optimize_cnn,
        space,
        algo=tpe.suggest,
        max_evals=int(MAX_EVALS)
    )
    tf.logging.info("Best: %s", best)
    return best


if __name__ == "__main__":
    """Plot the model and run the optimisation forever (and saves results)."""

    tf.logging.set_verbosity(tf.logging.DEBUG)

    # Print ENV Variables
    tf.logging.debug('=' * 20 + ' Environment Variables ' + '=' * 20)
    for k, v in os.environ.items():
        tf.logging.debug('{}: {}'.format(k, v))

    if not is_gpu_available():
        tf.logging.warning('GPUs are not available')

    tf.logging.info("Plotting a demo model that would represent "
          "a quite normal model (or a bit more huge), "
          "and then the best model...")

    plot_base_model()

    tf.logging.info("Now, we train many models, one after the other. "
          "Note that hyperopt has support for cloud "
          "distributed training using MongoDB.")

    tf.logging.info("\nYour results will be saved in the folder named 'results/'. "
          "You can sort that alphabetically and take the greatest one. "
          "As you run the optimization, results are consinuously saved into a "
          "'results.pkl' file, too. Re-running optimize.py will resume "
          "the meta-optimization.\n")

    # Optimize a new model with the TPE Algorithm:
    tf.logging.info("OPTIMIZING NEW MODEL:")
    try:
        best = run_a_trial()
        tf.logging.info(best)
        tf.logging.info("\nOPTIMIZATION STEP COMPLETE.\n")
    except Exception as err:
        err_str = str(err)
        tf.logging.info(err_str)
        traceback_str = str(traceback.format_exc())
        tf.logging.info(traceback_str)

    # Replot best model since it may have changed:
    tf.logging.info("PLOTTING BEST MODEL:")
    plot_best_model()
