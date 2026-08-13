from quality.adapters import predict_with_model


def predict(image, label_classes, inference_model=None):
    return predict_with_model(image, label_classes, inference_model)
