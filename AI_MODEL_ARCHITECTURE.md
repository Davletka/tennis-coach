# 🎾 AI-модель для обучения теннису: Архитектура и реализация

---

## 📋 Обзор

Текущая система анализирует технику видео-игроков через:
1. **Pose Detection** (MediaPipe) → извлекаются 33 точки тела
2. **Metrics Computation** → вычисляются углы суставов, скорости, положения
3. **Claude (LLM)** → генерирует коучинг на основе метрик

**Проблема:** Claude - это генеральный ИИ, который не специализирован на теннис-технике профессионального уровня.

**Решение:** Обучить специализированную ML-модель на видео профессиональных игроков, которая:
- Классифицирует тип удара (forehand, backhand, serve и т.д.)
- Сравнивает технику с профессиональным эталоном
- Предлагает конкретные улучшения на основе обучающей базы

---

## 🏗️ Предложенная архитектура

```
┌─────────────────────────────────────────────────────────────┐
│  Video Upload (User)                                       │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Frame Extraction & Pose Detection (MediaPipe)          │
│     → 33 landmarks per frame                               │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Metrics Computation                                     │
│     → Joint angles, velocities, CoM, torso rotation        │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
    ┌────────┴─────────┐
    │                  │
    ▼                  ▼
┌──────────────┐  ┌────────────────────────────────────┐
│ Current:     │  │ NEW: Technique Model               │
│ Claude API   │  │ ┌──────────────────────────────┐  │
│ (Chatbot)    │  │ │ 1. Event Classification     │  │
│              │  │ │    (Forehand/Backhand/Serve)│  │
└──────────────┘  │ ├──────────────────────────────┤  │
    │             │ │ 2. Technique Grader         │  │
    │             │ │    (0-100 points)           │  │
    │             │ ├──────────────────────────────┤  │
    │             │ │ 3. Anomaly Detector         │  │
    │             │ │    (vs. pro baseline)       │  │
    │             │ ├──────────────────────────────┤  │
    │             │ │ 4. Recommendation Engine    │  │
    │             │ │    (specific improvements)  │  │
    │             │ └──────────────────────────────┘  │
    │             └────────────────────────────────────┘
    │                  │
    └──────────┬───────┘
               ▼
    ┌─────────────────────────────────────────────┐
    │ Combine Results (Claude + Technique Model) │
    │ → Human-readable coaching report          │
    └──────────────────┬──────────────────────────┘
                       ▼
              ┌──────────────────────┐
              │ Coaching Report      │
              │ (User reads)         │
              └──────────────────────┘
```

---

## 📊 Компоненты для реализации

### 1️⃣ **Technique Model (TensorFlow/PyTorch)**

**Файл:** `pipeline/technique_model.py` (расширение)

```python
class TechniqueModel:
    """
    Специализированная модель для анализа техники теннис
    
    Входные данные: PerSwingMetrics (агрегированные метрики одного удара)
    Выходные данные: TechniquePrediction
    """
    
    def __init__(self, checkpoint_path=None):
        # Загружает pre-trained weights или инициализирует новую
        self.model = self._build_neural_network()
        if checkpoint_path:
            self.model.load_weights(checkpoint_path)
    
    def _build_neural_network(self):
        """
        Архитектура МНС для анализа техники
        
        Входной слой: 50 признаков (angles, velocities, positions)
        Скрытые слои: LSTM для temporal patterns
        Выходной слой: Multi-task output
            - Shot type classification (5 класс)
            - Technique score (0-100)
            - Key issues (binary flags)
        """
        pass
    
    def predict(self, per_swing_metrics: PerSwingMetrics) -> TechniquePrediction:
        """
        Предсказание для одного удара
        
        Возвращает:
        {
            'shot_type': 'forehand' | 'backhand' | 'serve' | 'volley' | 'slice',
            'overall_score': 78.5,  # 0-100
            'issues': {
                'early_preparation': True,
                'follow_through_incomplete': False,
                'wrist_unstable': True,
            },
            'pro_comparison': {
                'vs_federer': 0.82,  # similarity score
                'vs_nadal': 0.75,
            },
            'recommendations': [
                'Hold racket more vertically in backswing',
                'Extend follow-through longer',
            ]
        }
        """
        pass
    
    def train(self, training_data: List[TrainingSample], epochs=50):
        """
        Обучение модели на новых видео профессиональных игроков
        """
        pass
```

---

### 2️⃣ **Training Dataset Builder**

**Файл:** `pipeline/dataset_builder.py` (новый)

```python
class TrainingDatasetBuilder:
    """
    Собирает датасет из видео профессиональных игроков
    
    Требуемая структура видео:
    - /training_data/
      ├── federer/
      │   ├── forehand_01.mp4  (с меткой shot_type=forehand)
      │   ├── forehand_02.mp4
      │   └── backhand_01.mp4  (с меткой shot_type=backhand)
      ├── nadal/
      │   ├── forehand_01.mp4
      │   └── serve_01.mp4
      └── djokovic/
          └── ...
    """
    
    def extract_training_samples(self, video_dir: str) -> List[TrainingSample]:
        """
        Из каждого видео достаёт:
        1. Pose landmarks
        2. Метрики (углы, скорости)
        3. Label (shot_type, difficulty, player_level)
        
        Возвращает List[TrainingSample]
        """
        pass
    
    def augment_dataset(self, samples: List[TrainingSample]) -> List[TrainingSample]:
        """
        Аугментирует датасет:
        - Небольшие вариации углов (±2°)
        - Флипы видео (зеркальные удары)
        - Легкие искажения скорости
        """
        pass
```

---

### 3️⃣ **Model Integration Point**

**Файл:** `api/tasks/analyze.py` (расширение)

Место интеграции:

```python
# Уже в файле есть:
from pipeline.technique_model import get_model

# При анализе каждого удара:
technique_model = get_model()
model_prediction = technique_model.predict(per_swing_metrics)

# Модель вставляется в prompt к Claude:
user_prompt = _build_swing_prompt(
    psm, fps, 
    activity_cfg=activity_cfg,
    model_prediction=model_prediction  # ← СЮДА
)

# Claude получает информацию типа:
# "Модель предсказывает forehand с оценкой 72/100.
#  Основные проблемы: early preparation, instability.
#  Сравнение с профессионалом: 79% схожести с Federer.
#  Рекомендации..."
```

---

### 4️⃣ **Pro Baseline Reference Library**

**Файл:** `pipeline/pro_baseline.py` (новый)

```python
class ProBaselineLibrary:
    """
    Хранит технику профессиональных игроков как "эталоны"
    """
    
    def __init__(self):
        self.baselines = {
            'federer_forehand': {
                'ideal_angles': {...},
                'ideal_trajectory': [...],
                'key_points': [...]
            },
            'nadal_forehand': {...},
            'djokovic_backhand': {...},
            # ... и т.д.
        }
    
    def get_similarity(self, user_metrics: PerSwingMetrics, 
                       pro_key: str) -> float:
        """
        Возвращает 0-1 (насколько техника пользователя похожа на про)
        """
        pass
    
    def get_distance_to_ideal(self, user_metrics: PerSwingMetrics,
                             pro_key: str) -> Dict[str, float]:
        """
        Возвращает где именно отличается:
        {
            'preparation_angle': +5.2,  # user на 5.2° выше
            'follow_through': -3.1,     # user на 3.1° меньше
        }
        """
        pass
```

---

## 🚀 Этапы реализации

### **Этап 1: Подготовка (1-2 недели)**

1. Собрать/загрузить видео 10-15 профессиональных игроков
   - Разные типы ударов (forehand, backhand, serve, volley, slice)
   - Разные условия (медленные, быстрые, под давлением)
   
2. Разметить видео:
   ```
   {
     "shot_type": "forehand",
     "difficulty": 1-5,  // 5 = очень быстро
     "quality": "high" | "pro" | "advanced"
   }
   ```

3. Создать `TrainingSample` объекты для каждого удара

### **Этап 2: Модель (3-4 недели)**

1. Определить архитектуру (LSTM? Transformer? CNN?)
2. Обучить на профессиональных видео
3. Протестировать на любительских видео
4. Настроить гиперпараметры

### **Этап 3: Интеграция (1 неделя)**

1. Встроить предсказания модели в pipeline
2. Протестировать с Claude
3. Задеплоить в production

### **Этап 4: Улучшение (постоянно)**

- Собирать отзывы пользователей
- Перелучать модель ежемесячно
- Добавлять новые типы ударов

---

## 💡 Как это будет выглядеть для пользователя

**До (текущий Claude-only подход):**
```
Отзыв: "Ваша рука находилась под углом 142° в момент контакта. 
Рекомендуется снизить до 130-140°. Ротация торса была 38°."

❌ Пользователь не понимает, что это значит
```

**После (с Technique Model):**
```
Модель: Forehand [72/100]
Проблемы выявлены:
  ✗ Подготовка слишком поздняя (-0.3 сек vs Federer)
  ✓ Хороший контакт (79% vs Nadal)
  ✗ Follow-through короче (-8° vs профи)

Claude: "Хороший удар! Но начинай подготовку чуть раньше, 
как только противник ударит по мячу. Продолжай размах 
дальше, как бы провожая мяч в сетку."

✅ Ясно, конкретно, мотивирующе
```

---

## 🛠️ Минимальный MVP для запуска

Если начать с малого:

1. **Только классификация:**
   - Определяет forehand vs backhand (2 класса)
   - Просто - можно сделать за неделю
   
2. **Один про-эталон:**
   - Только Federer forehand (как идеал)
   - Сравнивает пользователя с этим одним
   
3. **Hard-coded rules:**
   - Не нейросеть, а IF-THEN-ELSE правила
   - "Если угол < X, то проблема Y"
   - Быстро воплотить, затем эволюционировать

---

## 📦 Зависимости

```toml
# В requirements-api.txt добавить:
tensorflow>=2.10.0      # для модели
optuna>=3.0.0           # hyperparameter tuning
scikit-learn>=1.0.0     # preprocessing
pandas>=1.3.0           # data handling
```

---

## 🔄 Обновление модели в production

```python
# api/tasks/retrain.py (новая Celery task)

@app.task(name="api.tasks.retrain_model")
def retrain_technique_model(max_datasets=500):
    """
    Ежемесячно переучивает модель на:
    - Новых видео пользователей (если они дали согласие)
    - Новых видео профессионалов
    - Корректировках от коучей
    """
    from pipeline.technique_model import TechniqueModel
    
    model = TechniqueModel()
    training_samples = collect_training_data(max_datasets)
    model.train(training_samples, epochs=50)
    model.save("production_weights_v2.h5")
    
    # Валидация перед заменой
    metrics = model.validate(test_set)
    if metrics.accuracy > 0.92:
        deploy_new_model("production_weights_v2.h5")
```

---

## 📈 Expected ROI

- **Точность анализа:** +40-50% (с ML vs Claude alone)
- **Удовлетворенность:** ✓ Пользователи видят "я улучшился"
- **Дифференциация:** Это ваше конкурентное преимущество vs других платформ
- **Масштабируемость:** Один раз обучили → используется для тысяч пользователей

---

## 🎓 Дополнительные идеи

1. **Transfer Learning:** Начать с модели, обученной на sports pose estimation, затем fine-tune на теннис
2. **3D Reconstruction:** Использовать multi-view для точнее análisis
3. **Player-specific models:** Хранить "биометрию" каждого пользователя (его "нормальна техика"), детектировать отклонения от его baseline
4. **Real-time feedback:** Когда модель работает быстро, можно давать фидбек ВО ВРЕМЯ тренировки, не ждя конца
5. **Gamification:** "You matched 82% of Federer's technique!" → мотивирует

---

## 📞 Контакты и вопросы

Если есть вопросы по архитектуре, спросите:
- Какой фреймворк выбрать (TensorFlow vs PyTorch)?
- Как организовать датасет?
- Как быстро заболучить первые результаты?

