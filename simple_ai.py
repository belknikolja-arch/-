import numpy as np
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import accuracy_score, classification_report

def create_simple_ai():
    """
    Создает и обучает простую нейронную сеть для классификации цветов ириса.
    Это базовый пример искусственного интеллекта.
    """
    print("Загрузка данных...")
    # Загружаем известный набор данных Iris (цветы ириса)
    data = load_iris()
    X = data.data  # Признаки (размеры чашелистиков и лепестков)
    y = data.target  # Метки (виды цветов)

    # Разделяем данные на обучающую и тестовую выборки
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    # Масштабируем данные (важно для нейронных сетей)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    print("Создание архитектуры нейронной сети...")
    # Создаем модель нейронной сети (Многослойный перцептрон)
    # hidden_layer_sizes=(10, 5) означает 2 скрытых слоя с 10 и 5 нейронами соответственно
    ai_model = MLPClassifier(
        hidden_layer_sizes=(10, 5), 
        max_iter=1000, 
        random_state=42, 
        solver='adam',
        activation='relu'
    )

    print("Обучение ИИ...")
    # Обучаем модель
    ai_model.fit(X_train_scaled, y_train)

    print("Тестирование ИИ...")
    # Делаем предсказания на тестовых данных
    predictions = ai_model.predict(X_test_scaled)

    # Оцениваем точность
    accuracy = accuracy_score(y_test, predictions)
    
    print("\n" + "="*40)
    print(f"Точность модели: {accuracy * 100:.2f}%")
    print("="*40)
    print("\nОтчет о классификации:")
    print(classification_report(y_test, predictions, target_names=data.target_names))

    # Пример использования
    print("\nПример предсказания на новых данных:")
    sample = np.array([[5.1, 3.5, 1.4, 0.2]]) # Данные одного цветка
    sample_scaled = scaler.transform(sample)
    prediction = ai_model.predict(sample_scaled)
    predicted_class = data.target_names[prediction[0]]
    print(f"Для входных данных {sample[0]} ИИ предсказывает вид: {predicted_class}")

    return ai_model, scaler

if __name__ == "__main__":
    try:
        model, scaler = create_simple_ai()
        print("\nИИ успешно создан и протестирован!")
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        print("Убедитесь, что установлены необходимые библиотеки:")
        print("pip install scikit-learn numpy")
