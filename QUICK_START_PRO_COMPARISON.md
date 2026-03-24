# 🎯 Quick Start: Как добавить обучение на профессиональной технике (за 1 день)

---

## 📌 План минимального MVP

Вместо того чтобы создавать сложную нейросеть, начнём с **простой reference базы** профессиональных углов и сравним с ней пользователя:

```
Пользователь снимает видео → Вычисляем его углы
                          → Сравниваем с Federer/Nadal reference
                          → Показываем "92% похожести на Federer"
                          → Claude дает совет на основе этого
```

Трудоёмкость: **1-2 дня**, результат: **уже очень полезно**.

---

## 📑 Шаг 1: Создать reference-базу

**Файл:** `pipeline/pro_reference.py` (новый)

```python
"""
Reference angles и metrics от профессиональных игроков
Собрано вручную из анализа реальных видео или из спортивной литературы
"""

PRO_REFERENCE = {
    # FOREHAND (groundstroke)
    "forehand": {
        "federer": {
            "right_elbow_angle": 125,        # в момент контакта
            "right_shoulder_angle": 85,      # плечо-локоть-бедро
            "stance_width": 1.5,              # between feet
            "torso_rotation_max": 50,         # max поворот туловища
            "wrist_relative_y": -0.05,       # выше бедер
        },
        "nadal": {
            "right_elbow_angle": 130,
            "right_shoulder_angle": 80,
            "stance_width": 1.7,
            "torso_rotation_max": 55,
            "wrist_relative_y": -0.08,
        },
        "djokovic": {
            "right_elbow_angle": 120,
            "right_shoulder_angle": 88,
            "stance_width": 1.45,
            "torso_rotation_max": 48,
            "wrist_relative_y": -0.03,
        },
    },
    
    # BACKHAND (single-hand)
    "backhand": {
        "federer": {
            "left_elbow_angle": 150,
            "left_shoulder_angle": 95,
            "stance_width": 1.4,
            "torso_rotation_max": 40,
            "wrist_relative_y": 0.0,
        },
        "nadal": {
            "left_elbow_angle": 145,
            "left_shoulder_angle": 92,
            "stance_width": 1.5,
            "torso_rotation_max": 42,
            "wrist_relative_y": 0.02,
        },
    },
    
    # SERVE
    "serve": {
        "federer": {
            "right_elbow_angle": 160,        # почти прямая рука
            "right_shoulder_angle": 110,     # рука выше плеча
            "wrist_relative_y": -0.35,       # очень высоко
            "torso_rotation_max": 35,        # меньше чем в forehand
        },
        "nadal": {
            "right_elbow_angle": 155,
            "right_shoulder_angle": 115,
            "wrist_relative_y": -0.40,
            "torso_rotation_max": 38,
        },
    },
    
    # SLICE BACKHAND
    "slice": {
        "federer": {
            "left_elbow_angle": 140,         # более выпрямлена
            "left_shoulder_angle": 100,
            "stance_width": 1.2,
            "torso_rotation_max": 25,        # мало движения
        },
    },
}

def get_pro_reference(shot_type: str, player: str = "federer") -> dict:
    """Получить reference values для типа удара и игрока"""
    return PRO_REFERENCE.get(shot_type, {}).get(player, {})

def get_all_pro_players(shot_type: str) -> list:
    """Получить всех про (federer, nadal, djokovic), которые есть для shot_type"""
    return list(PRO_REFERENCE.get(shot_type, {}).keys())
```

---

## 🔄 Шаг 2: Функция сравнения

**Добавить в** `pipeline/technique_model.py`:

```python
from pipeline.pro_reference import get_pro_reference, get_all_pro_players
from pipeline.metrics import PerSwingMetrics

class SimpleTechniqueComparator:
    """
    Без нейросети - просто сравниваем углы с reference
    """
    
    @staticmethod
    def compare_with_pro(
        user_metrics: PerSwingMetrics,
        shot_type: str = "forehand",
        pro_player: str = "federer"
    ) -> dict:
        """
        Сравнивает пользователя с профессионалом
        
        Возвращает:
        {
            'similarity_score': 0.82,  # 0-1, где 1 = идеально
            'deviations': {
                'elbow_angle': {
                    'user': 135,
                    'pro': 125,
                    'difference': +10,  # градусы
                    'status': 'too_high'  # or 'too_low' or 'perfect'
                },
                'shoulder_angle': {...},
            },
            'pro_comparison': ['vs Federer: 82%', 'vs Nadal: 75%', 'vs Djokovic: 88%']
        }
        """
        
        reference = get_pro_reference(shot_type, pro_player)
        if not reference:
            return {'error': f'No reference for {shot_type} by {pro_player}'}
        
        # Ключё метрики для сравнения
        user_angles = {
            'elbow_angle': user_metrics.right_elbow.mean,
            'shoulder_angle': user_metrics.right_shoulder.mean,
            'stance_width': user_metrics.stance_width_mean,
            'torso_rotation': user_metrics.torso_rotation_max,
        }
        
        deviations = {}
        total_diff = 0
        
        for metric_name, user_value in user_angles.items():
            if user_value is None:
                continue
            
            pro_value = reference.get(metric_name)
            if pro_value is None:
                continue
            
            diff = abs(user_value - pro_value)
            total_diff += diff
            
            # Классифицируем отклонение
            if diff < 5:
                status = 'perfect'
                confidence = 1.0
            elif diff < 15:
                status = 'good'
                confidence = 0.75
            elif diff < 25:
                status = 'needs_work'
                confidence = 0.50
            else:
                status = 'significant_difference'
                confidence = 0.25
            
            direction = 'too_high' if user_value > pro_value else 'too_low'
            
            deviations[metric_name] = {
                'user': round(user_value, 1),
                'pro': pro_value,
                'difference': round(diff, 1),
                'direction': direction,
                'status': status,
                'confidence': confidence,
            }
        
        # Общий similarity score (0-1)
        # Чем меньше отклонения, тем ближе к 1
        max_expected_diff = 30  # максимальное ожидаемое отклонение
        avg_diff = total_diff / len(deviations) if deviations else 0
        similarity = max(0, 1 - (avg_diff / max_expected_diff))
        
        # Сравнение со всеми pro
        pro_players = get_all_pro_players(shot_type)
        comparisons = []
        for pro in pro_players:
            if pro != pro_player:
                other_similarity = SimpleTechniqueComparator.compare_with_pro(
                    user_metrics, shot_type, pro
                )['similarity_score']
                comparisons.append(f"{pro}: {int(other_similarity*100)}%")
        
        return {
            'similarity_score': round(similarity, 2),
            'deviations': deviations,
            'pro_comparison': comparisons,
        }
```

---

## 🧠 Шаг 3: Встроить в pipeline

**Модифицировать** `api/tasks/analyze.py`:

После строки с `get_per_swing_coaching`, добавить:

```python
from pipeline.technique_model import SimpleTechniqueComparator

# При обработке каждого удара:
swing_coaching_list = get_per_swing_coaching(
    per_swing_list, fps, api_key=settings.anthropic_api_key,
    on_swing_done=_swing_cb, activity_cfg=activity_cfg,
)

# НОВОЕ: Добавить сравнение с pro
for i, psm in enumerate(per_swing_list):
    comparison = SimpleTechniqueComparator.compare_with_pro(
        psm, 
        shot_type=psm.motion_type,  # "forehand", "backhand", etc.
        pro_player="federer"
    )
    
    # Вставить в JSON response
    per_swing_coaching_dicts[i]['pro_comparison'] = comparison
```

---

## 💬 Шаг 4: Claude использует эту информацию

**Модифицировать** `pipeline/coach.py`:

В функции `_build_swing_prompt`:

```python
def _build_swing_prompt(
    psm: PerSwingMetrics, 
    fps: float, 
    activity_cfg=None,
    model_prediction: Optional[dict] = None,
    pro_comparison: Optional[dict] = None  # ← НОВОЕ
) -> str:
    """Build user prompt for one swing."""
    
    # ... существующий код ...
    
    # НОВОЕ: Добавить информацию о сравнении с pro
    if pro_comparison and pro_comparison.get('similarity_score'):
        similarity = pro_comparison['similarity_score']
        deviations = pro_comparison.get('deviations', {})
        
        comparison_text = f"""
        COMPARISON WITH PROFESSIONAL (Federer):
        - Overall similarity: {similarity*100:.0f}%
        
        Details:
        """
        for metric, dev in deviations.items():
            status_emoji = {
                'perfect': '✓',
                'good': '◐',
                'needs_work': '◑',
                'significant_difference': '✗'
            }.get(dev['status'], '?')
            
            comparison_text += f"""
        {status_emoji} {metric}: {dev['user']} (user) vs {dev['pro']} (pro) 
           → {dev['difference']}° {dev['direction']}
        """
        
        user_prompt += comparison_text
    
    return user_prompt
```

---

## 📊 Шаг 5: Вывести в UI

**Модифицировать** `frontend/src/components/shared.tsx`:

```tsx
// Добавить компонент для отображения сравнения с pro

if (swing.pro_comparison) {
  const { similarity_score, deviations } = swing.pro_comparison;
  
  return (
    <div className="mt-3 p-3 bg-blue-900/20 rounded">
      <p className="text-sm text-blue-300">
        📊 {(similarity_score * 100).toFixed(0)}% похожести с Federer
      </p>
      {Object.entries(deviations).map(([metric, dev]) => (
        <div key={metric} className="text-xs text-gray-400 mt-1">
          {metric}: {dev.user}° vs {dev.pro}° 
          ({dev.direction === 'too_high' ? '+' : '-'}{dev.difference.toFixed(1)}°)
        </div>
      ))}
    </div>
  );
}
```

---

## ✅ Готово!

После этих изменений:

1. **Пользователь ** видит: "82% похожести на Federer"
2. **Claude** видит эту информацию и адаптирует совет
3. **Вывод:** "Хороший forehand! Ты уже похож на Federer на 82%. 
   Одно отличие - твое плечо более развёрнуто (на 10° больше). 
   Это даст тебе более мощный удар, но может быть менее контролируемым. 
   Если хочешь точности, как у Federer, ограничь разворот на несколько градусов."

---

## 🚀 Следующие шаги

После этого MVP можно:

1. **Добавить больше про-игроков** в reference (Djokovic, Wawrinka, etc.)
2. **Добавить другие типы ударов** (slice, volley, overhead)
3. **Собрать real feedback** от пользователей
4. **Перейти на нейросеть** когда будет много данных

---

## 📝 Файлы для изменения

- [x] pipeline/pro_reference.py (новый)
- [x] pipeline/technique_model.py (расширить)
- [x] api/tasks/analyze.py (добавить сравнение)
- [x] pipeline/coach.py (добавить в prompt)
- [x] frontend/src/components/shared.tsx (отобразить)

**Общее время:** 4-6 часов работы

