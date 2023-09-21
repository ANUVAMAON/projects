'''Cats & Dogs image prediction using keras.VGG16'''

# %%
import tensorflow as tf
from keras.preprocessing.image import ImageDataGenerator
from keras.applications import VGG16
from keras.applications.vgg16 import preprocess_input
from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, Flatten

batch_size = 64

datagen = ImageDataGenerator(rescale=1.0/255,
                             preprocessing_function=tf.keras.applications.vgg16.preprocess_input,
                             validation_split=0.2)

train_gen = datagen.flow_from_directory(
    'dogs-vs-cats/train',
    target_size=(370, 370),
    batch_size=batch_size,
    class_mode='categorical',
    subset='training'
)

val_gen = datagen.flow_from_directory(
    'dogs-vs-cats/train',
    target_size=(370, 370),
    batch_size=batch_size,
    class_mode='categorical',
    subset='validation'
)

# %%
vgg16_model = tf.keras.applications.vgg16.VGG16(include_top=False, input_shape=(370, 370, 3))

for layer in vgg16_model.layers:
    layer.trainable = False

# %%
flat = tf.keras.layers.Flatten()(vgg16_model.output)
dropout1 = tf.keras.layers.Dropout(0.2, name="Dropout1") (flat)
dense1 = tf.keras.layers.Dense(128, activation='relu', name="Dense1") (dropout1)
dropout2 = tf.keras.layers.Dropout(0.2, name="Dropout2") (dense1)
output = tf.keras.layers.Dense(2, activation='softmax', name="Output") (dropout2)

final_model = tf.keras.models.Model(inputs=[vgg16_model.input], outputs=[output])

final_model.summary()

# %%
final_model.compile(optimizer='adam', loss=tf.keras.losses.categorical_crossentropy, metrics=['accuracy'])

# %%
learning_rate_reduction = tf.keras.callbacks.ReduceLROnPlateau(monitor='val_accuracy',
                                            patience=2,
                                            factor=0.5,
                                            min_lr=0.00001,
                                            verbose=1)
early_stoping = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True, verbose=0)

# %%
final_model.fit(train_gen,
                epochs=20,
                batch_size=batch_size,
                validation_data=val_gen,
                callbacks=[learning_rate_reduction, early_stoping])

# %%
test_loss, test_acc = final_model.evaluate(val_gen)

print(f"Test accuracy: {test_acc}")

final_model.save(f"dogs_cats_2_11092023_acc{test_acc}.h5")
