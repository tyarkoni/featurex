''' Extractor classes based on pre-trained models. '''

import numpy as np
from abc import ABCMeta

from pliers.extractors.image import ImageExtractor
from pliers.extractors.base import Extractor, ExtractorResult
from pliers.filters.image import ImageResizingFilter
from pliers.stimuli import ImageStim, TextStim
from pliers.utils import (attempt_to_import, verify_dependencies,
                         listify)

tf = attempt_to_import('tensorflow')
attempt_to_import('tensorflow.keras')
hub = attempt_to_import('tensorflow_hub')


class TFHubExtractor(Extractor, metaclass=ABCMeta):

    ''' A generic class for Tensorflow Hub extractors 
    Args:
        url_or_path (str): url or path to TFHub model
        task (str): model task/domain identifier
        labels (optional): list of labels (if relevant, e.g. for 
            classification models).
        kwargs (dict): arguments to hub.KerasLayer'''

    _log_attributes = ('url_or_path',)
    
    def __init__(self, url_or_path, task=None, labels=None, **kwargs):
        verify_dependencies(['tensorflow', 'tensorflow_hub'])
        self.model = hub.KerasLayer(url_or_path, **kwargs)
        self._labels = labels
        self._task = task
        super().__init__()

    def _get_feature_names(self): # to be edited
        if self._labels:
            return self._labels
        else:
            return listify(self._task)
    
    def _preprocess(self, stim):
        return stim.data

    def _postprocess(self, out):
        return out
        
    def _extract(self, stim):
        features = listify(self._get_feature_names())
        inp = self._preprocess(stim)
        out = self.model(inp).numpy()
        out = self._postprocess(out)
        return ExtractorResult(out, stim, self, 
                               features=features)


class TFHubImageExtractor(TFHubExtractor):

    ''' Extractor class for image models
    Args:
        rescale_rgb (bool): whether to rescale values to 0-1 range
        reshape_input (tuple): if input needs to be reshaped, 
            specifies target shape (height, width, n_channels).
            Details on whether the model only accept a fixed size are
            usually provided on the TFHub model page. 
    '''

    _input_type = ImageStim

    def __init__(self, rescale_rgb=True, reshape_input=None): # add other args?
        super().__init__()
        self.rescale_rgb = rescale_rgb
        self.reshape_input = reshape_input

    def _preprocess(self, stim):
        if self.reshape_input:
            resizer = ImageResizingFilter(size=self.reshape_input[:-1]) # check dims
            x = resizer.transform(stim).data
        else:
            x = stim.data
        if self.rescale_rgb:
            x = x / 255.0 # check
        x = tf.convert_to_tensor(x, 
                                 type=tf.float32)
        x = tf.expand_dims(x, axis=0)
        return x


class TFHubImageEmbeddingExtractor(TFHubImageExtractor):

    _task = 'embedding'
    # Add task-specific postprocessing


class TFHubImageClassificationExtractor(TFHubImageExtractor):

    _task = 'classification'
    # Add task-specific postprocessing


class TFHubTextExtractor(TFHubExtractor):

    ''' Extractor class for text input '''

    _input_type = TextStim

    def __init__(self, preprocessor_url_or_path=None):
        super().__init__()
        self.preprocessor_url_or_path=preprocessor_url_or_path

    def _preprocess(self, stim):
        x = listify(stim.data)
        if self.preprocessor_url_or_path:
            preprocessor = hub.KerasLayer(self.preprocessor_url_or_path)
            x = preprocessor(x)
        return x


class TFHubTextEmbeddingExtractor(TFHubTextExtractor):

    _task = 'embedding'

    def __init__(self, output_key='default'):
        super().__init__()
        self.output_key = output_key

    def _postprocess(self, out):
        return out[self.output_key]


class TensorFlowKerasApplicationExtractor(ImageExtractor):

    ''' Labels objects in images using a pretrained Inception V3 architecture
    implemented in TensorFlow / Keras.

    Images must be RGB and be a certain shape. Different model architectures
    may require different shapes, and images will be resized (with some
    distortion) if the shape of the image is different.

    Args:
        architecture (str): model architecture to use. One of 'vgg16', 'vgg19',
            'resnet50', 'inception_resnetv2', 'inceptionv3', 'xception',
            'densenet121', 'densenet169', 'nasnetlarge', or 'nasnetmobile'.
        weights (str): URL to download pre-trained weights. If None (default),
            uses the pre-trained weights trained on ImageNet used in Keras
            Applications.
        num_predictions (int): Number of top predicted labels to retain for
            each image.
     '''

    _log_attributes = ('architecture', 'weights', 'num_predictions')
    VERSION = '1.0'

    def __init__(self,
                 architecture='inceptionv3',
                 weights=None,
                 num_predictions=5):
        verify_dependencies(['tensorflow'])
        verify_dependencies(['tensorflow.keras'])
        super().__init__()

        # Model name: (model module, model function, required shape).
        apps = tf.keras.applications
        model_mapping = {
            'vgg16': (apps.vgg16, apps.vgg16.VGG16, (224, 224, 3)),
            'vgg19': (apps.vgg19, apps.VGG19, (224, 224, 3)),
            'resnet50': (apps.resnet50, apps.resnet50.ResNet50, (224, 224, 3)),
            'inception_resnetv2': (
                apps.inception_resnet_v2,
                apps.inception_resnet_v2.InceptionResNetV2, (299, 299, 3)),
            'inceptionv3': (
                apps.inception_v3, apps.inception_v3.InceptionV3,
                (299, 299, 3)),
            'xception': (apps.xception, apps.xception.Xception, (299, 299, 3)),
            'densenet121': (
                apps.densenet, apps.densenet.DenseNet121, (224, 224, 3)),
            'densenet169': (
                apps.densenet, apps.densenet.DenseNet169, (224, 224, 3)),
            'densenet201': (
                apps.densenet, apps.densenet.DenseNet201, (224, 224, 3)),
            'nasnetlarge': (
                apps.nasnet, apps.nasnet.NASNetLarge, (331, 331, 3)),
            'nasnetmobile': (
                apps.nasnet, apps.nasnet.NASNetMobile, (224, 224, 3)),
        }
        if weights is None:
            weights = 'imagenet'
        if architecture.lower() not in model_mapping.keys():
            raise ValueError(
                "Unknown architecture '{}'. Available arhitectures are '{}'."
                .format(architecture, "', '".join(model_mapping.keys())))

        self.architecture = architecture.lower()
        self.weights = weights
        self.num_predictions = num_predictions

        # The preprocessing and decoding functions are in the module.
        self._model_module = model_mapping[self.architecture][0]
        # Instantiating the model also downloads the weights to a cache.
        self.model = model_mapping[self.architecture][1](weights=self.weights)
        self._required_shape = model_mapping[self.architecture][2]

    def _extract(self, stim):
        x = stim.data
        if x.ndim != 3:
            raise ValueError(
                "Stim data must have rank 3 but got rank {}".format(x.ndim))
        if x.shape != self._required_shape:
            resizer = ImageResizingFilter(size=self._required_shape[:-1])
            x = resizer.transform(stim).data
        # Add batch dimension.
        x = x[None]
        # Normalize the features.
        x = self._model_module.preprocess_input(x)
        preds = self.model.predict(x, batch_size=1)

        # This produces a nested list. There is one sub-list per sample in the
        # batch, and each sub-list contains `self.num_predictions` tuples with
        # `(ID, human-readable-label, probability)`.
        decoded = self._model_module.decode_predictions(
            preds, top=self.num_predictions)

        # We assume there is only one sample in the batch.
        decoded = decoded[0]
        values = [t[2] for t in decoded]
        features = [t[1] for t in decoded]

        return ExtractorResult([values], stim, self, features=features)
