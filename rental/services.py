import json
import logging
from django.conf import settings
from django.db.models import Q
from .models import Product
from typing import List, Dict, Any

# Безопасный импорт openai
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class SmartSearchService:
    """
    Сервис для умного поиска товаров с использованием ChatGPT API
    """
    
    def __init__(self):
        self.api_available = OPENAI_AVAILABLE
        self.api_configured = False
        
        if self.api_available:
            # Инициализация OpenAI API
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
            if api_key and api_key.strip():
                openai.api_key = api_key.strip()
                self.api_configured = True
                logger.info("OpenAI API ключ настроен успешно")
            else:
                logger.warning("OPENAI_API_KEY не установлен в настройках")
        else:
            logger.warning("OpenAI библиотека не установлена. pip install openai==0.28.1")
    
    def get_all_products_for_context(self) -> List[Dict[str, Any]]:
        """
        Получает все товары из базы данных для передачи в контекст ChatGPT
        """
        products = Product.objects.all().values(
            'id', 'name', 'description', 'article'
        )
        
        product_context = []
        for product in products:
            # Создаем краткое описание товара для ChatGPT
            product_info = {
                'id': product['id'],
                'name': product['name'].capitalize() if product['name'] else '',
                'description': product['description'].capitalize() if product['description'] else '',
                'article': product['article']
            }
            product_context.append(product_info)
        
        return product_context
    
    def analyze_product_catalog(self) -> Dict[str, List[str]]:
        """
        Анализирует каталог товаров для автоматического создания связей
        """
        products = Product.objects.all()
        
        # Словарь для группировки товаров по категориям
        categories = {}
        
        # Анализируем названия товаров для поиска общих слов
        for product in products:
            name_words = product.name.lower().split()
            description_words = product.description.lower().split() if product.description else []
            
            all_words = set(name_words + description_words)
            
            for word in all_words:
                if len(word) > 3:  # Игнорируем короткие слова
                    if word not in categories:
                        categories[word] = []
                    categories[word].append({
                        'id': product.id,
                        'name': product.name,
                        'description': product.description
                    })
        
        # Находим слова, которые встречаются в нескольких товарах
        related_words = {}
        for word, products_list in categories.items():
            if len(products_list) > 1:  # Слово встречается в нескольких товарах
                related_words[word] = [p['name'] for p in products_list]
        
        logger.info(f"Найдено {len(related_words)} связанных категорий в каталоге")
        return related_words
    
    def expand_search_query(self, query: str) -> str:
        """
        Расширяет поисковый запрос синонимами и связанными терминами
        """
        query_lower = query.lower().strip()
        
        # Словарь расширений для общих терминов
        expansions = {
            # Мебель и сидение
            'сиденье': 'сиденье стул кресло мебель для сидения табурет',
            'стул': 'стул сиденье кресло табурет мебель',
            'кресло': 'кресло стул сиденье мебель',
            'парта': 'парта стол рабочая поверхность столешница письменный стол',
            'стол': 'стол парта поверхность столешница рабочий стол письменный стол',
            'мебель': 'мебель стол стул кресло шкаф полка',
            
            # Освещение
            'свет': 'свет освещение лампа светильник источник света яркость',
            'освещение': 'освещение свет лампа светильник LED панель софтбокс',
            'лампа': 'лампа светильник освещение свет источник света',
            'яркость': 'яркость освещение свет лампа светильник',
            
            # Техника и устройства
            'камера': 'камера фотоаппарат видеокамера съемка фото видео',
            'фото': 'фото камера фотоаппарат съемка изображение',
            'видео': 'видео камера видеокамера съемка запись',
            'съемка': 'съемка камера фото видео фотоаппарат видеокамера',
            
            # Звук
            'звук': 'звук аудио микрофон динамик наушники запись голос',
            'аудио': 'аудио звук микрофон динамик наушники',
            'микрофон': 'микрофон звук аудио голос запись',
            'голос': 'голос микрофон звук аудио запись',
            
            # Поддержка и стабилизация
            'штатив': 'штатив подставка опора поддержка стабилизация устойчивость',
            'подставка': 'подставка штатив опора поддержка держатель',
            'опора': 'опора штатив подставка поддержка устойчивость',
            'устойчивость': 'устойчивость штатив опора подставка поддержка',
            
            # Экраны и мониторы
            'экран': 'экран монитор дисплей показ отображение',
            'монитор': 'монитор экран дисплей показ',
            'дисплей': 'дисплей монитор экран показ отображение',
            
            # Хранение и организация
            'хранение': 'хранение шкаф полка ящик контейнер организация',
            'полка': 'полка хранение шкаф стеллаж',
            'шкаф': 'шкаф хранение полка мебель',
            
            # Материалы
            'дерево': 'дерево деревянный мебель натуральный',
            'металл': 'металл металлический железо стальной',
            'пластик': 'пластик пластиковый синтетический',
            'стекло': 'стекло стеклянный прозрачный',
            
            # Размеры и характеристики
            'большой': 'большой крупный широкий просторный',
            'маленький': 'маленький компактный мини портативный',
            'портативный': 'портативный переносной мобильный компактный маленький',
            'компактный': 'компактный маленький портативный мини',
            
            # Цвета
            'белый': 'белый светлый',
            'черный': 'черный темный',
            'красный': 'красный',
            'синий': 'синий голубой',
            'зеленый': 'зеленый',
        }
        
        # Проверяем каждое слово в запросе
        words = query_lower.split()
        expanded_terms = set([query_lower])  # Добавляем оригинальный запрос
        
        for word in words:
            if word in expansions:
                expanded_terms.update(expansions[word].split())
            # Также ищем частичные совпадения
            for key, value in expansions.items():
                if word in key or key in word:
                    expanded_terms.update(value.split())
        
        # Возвращаем расширенный запрос
        return ' '.join(expanded_terms)
    
    def create_enhanced_search_prompt(self, original_query: str, expanded_query: str, products: List[Dict[str, Any]]) -> str:
        """
        Создает улучшенный промпт с использованием расширенного запроса
        """
        products_text = "\n".join([
            f"ID: {p['id']}, Название: {p['name']}, Описание: {p['description']}, Артикул: {p['article']}"
            for p in products
        ])
        
        prompt = f"""
Ты - эксперт по поиску товаров с глубоким пониманием семантических связей между словами и предметами.

ОРИГИНАЛЬНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ: "{original_query}"
РАСШИРЕННЫЕ ПОИСКОВЫЕ ТЕРМИНЫ: "{expanded_query}"

Доступные товары:
{products_text}

ИНСТРУКЦИИ:
1. Анализируй КАЖДЫЙ товар на предмет соответствия запросу
2. Ищи связи по:
   - Названию товара
   - Описанию товара  
   - Функциональному назначению
   - Области применения
   - Материалам и характеристикам
   - Синонимам и альтернативным названиям

3. ВКЛЮЧАЙ товар в результат, если найдена ЛЮБАЯ логическая связь с запросом

4. Будь максимально креативным в поиске связей

Примеры творческого мышления:
- "сиденье" → стул (прямая связь), кресло (синоним), скамейка (для сидения)
- "парта" → стол (синоним), любая рабочая поверхность
- "яркий" → лампы, мониторы, светлые предметы
- "мягкий" → подушки, кресла, текстильные изделия
- "прочный" → металлические предметы, качественная мебель

Верни результат в JSON:
{{
    "relevant_products": [список ID товаров],
    "reasoning": "детальное объяснение найденных связей для каждого товара"
}}
"""
        return prompt
        """
        Создает продвинутый промпт для ChatGPT с учетом запроса пользователя и доступных товаров
        """
        products_text = "\n".join([
            f"ID: {p['id']}, Название: {p['name']}, Описание: {p['description']}, Артикул: {p['article']}"
            for p in products
        ])
        
        prompt = f"""
Ты - эксперт по поиску товаров с глубоким пониманием семантических связей между словами и предметами.
Твоя задача - найти ВСЕ товары из списка, которые хоть как-то связаны с поисковым запросом пользователя.

ВАЖНО: Ты должен выбирать ТОЛЬКО из товаров в списке ниже. НЕ придумывай новые товары.

Поисковый запрос: "{query}"

Доступные товары:
{products_text}

ИНСТРУКЦИИ ДЛЯ АНАЛИЗА:

1. ПРЯМЫЕ СОВПАДЕНИЯ: Ищи точные и частичные совпадения слов

2. СИНОНИМЫ И АЛЬТЕРНАТИВНЫЕ НАЗВАНИЯ:
   - стул ↔ сиденье, кресло, мебель для сидения
   - стол ↔ парта, поверхность, рабочая поверхность, столешница
   - лампа ↔ светильник, освещение, источник света
   - камера ↔ фотоаппарат, видеокамера, съемочное устройство
   - микрофон ↔ звукозапись, аудио, голос

3. ФУНКЦИОНАЛЬНЫЕ СВЯЗИ:
   - "для сидения" → стулья, кресла, скамейки
   - "для работы" → столы, парты, рабочие поверхности
   - "освещение" → любые источники света
   - "съемка" → камеры, объективы, штативы, освещение
   - "звук" → микрофоны, динамики, наушники

4. КАТЕГОРИЙНЫЕ СВЯЗИ:
   - "мебель" → столы, стулья, шкафы, полки
   - "техника" → камеры, компьютеры, телефоны
   - "инструменты" → любые рабочие инструменты

5. КОНТЕКСТУАЛЬНЫЕ СВЯЗИ:
   - "студия" → освещение, камеры, фоны, мебель
   - "офис" → столы, стулья, техника
   - "дом" → мебель, техника, освещение

6. МАТЕРИАЛЫ И ЧАСТИ:
   - "дерево" → деревянная мебель
   - "металл" → металлические изделия
   - "стекло" → стеклянные поверхности

7. ДЕЙСТВИЯ И ПРОЦЕССЫ:
   - "писать" → столы, парты
   - "сидеть" → стулья, кресла
   - "освещать" → лампы, светильники

БУДЬ МАКСИМАЛЬНО КРЕАТИВНЫМ в поиске связей! Если есть хоть малейшая логическая связь между запросом и товаром - включай его в результат.

Примеры креативного мышления:
- Запрос "сиденье" → стул (прямая связь), кресло (синоним), подушка (для сидения)
- Запрос "парта" → стол (синоним), рабочая поверхность (функция)
- Запрос "яркость" → лампа, светильник, монитор
- Запрос "устойчивость" → штатив, подставка, стул
- Запрос "портативный" → любые переносные устройства

Верни результат СТРОГО в JSON формате:
{{
    "relevant_products": [список ID товаров],
    "reasoning": "подробное объяснение найденных связей"
}}

Если подходящих товаров нет, верни пустой список в relevant_products.
"""
        return prompt
    
    def search_with_chatgpt(self, query: str) -> List[int]:
        """
        Выполняет улучшенный поиск товаров с помощью ChatGPT API
        """
        if not self.api_available:
            logger.warning("OpenAI библиотека не доступна, используется обычный поиск")
            return self.fallback_search(query)
            
        if not self.api_configured:
            logger.warning("OpenAI API ключ не настроен, используется обычный поиск")
            return self.fallback_search(query)
        
        try:
            # Получаем все товары для контекста
            products = self.get_all_products_for_context()
            
            if not products:
                logger.warning("Нет товаров в базе данных")
                return []
            
            # Расширяем поисковый запрос
            expanded_query = self.expand_search_query(query)
            logger.info(f"Оригинальный запрос: '{query}' → Расширенный: '{expanded_query}'")
            
            # Создаем улучшенный промпт
            prompt = self.create_enhanced_search_prompt(query, expanded_query, products)
            
            logger.info(f"Отправка расширенного запроса в ChatGPT")
            
            # Отправляем запрос к ChatGPT с более высокой температурой для креативности
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": """Ты - эксперт по семантическому поиску с глубоким пониманием связей между предметами и понятиями. 
                        Твоя задача - найти ВСЕ возможные связи между запросом пользователя и товарами в каталоге.
                        Будь максимально креативным и включай товары даже при слабых, но логически обоснованных связях."""
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,  # Увеличили лимит для более подробного анализа
                temperature=0.7,  # Увеличили для большей креативности
                timeout=30
            )
            
            # Парсим ответ
            response_text = response.choices[0].message.content.strip()
            logger.info(f"ChatGPT ответ получен: {len(response_text)} символов")
            
            try:
                result = json.loads(response_text)
                product_ids = result.get('relevant_products', [])
                reasoning = result.get('reasoning', '')
                
                logger.info(f"Умный поиск нашел товаров: {len(product_ids)}")
                logger.info(f"Обоснование: {reasoning}")
                
                # Валидируем ID товаров
                valid_ids = []
                existing_ids = set(Product.objects.values_list('id', flat=True))
                
                for product_id in product_ids:
                    if isinstance(product_id, int) and product_id in existing_ids:
                        valid_ids.append(product_id)
                
                logger.info(f"Валидных ID найдено: {len(valid_ids)}")
                
                # Если ничего не найдено умным поиском, попробуем fallback с расширенным запросом
                if not valid_ids:
                    logger.info("Умный поиск не дал результатов, пробуем fallback с расширенным запросом")
                    return self.fallback_search(expanded_query)
                
                return valid_ids
                
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON ответа от ChatGPT: {e}")
                logger.error(f"Ответ ChatGPT: {response_text}")
                # Пробуем fallback с расширенным запросом
                return self.fallback_search(self.expand_search_query(query))
                
        except Exception as e:
            logger.error(f"Ошибка при обращении к ChatGPT: {e}")
            # Пробуем fallback с расширенным запросом
            return self.fallback_search(self.expand_search_query(query))
    
    def fallback_search(self, query: str) -> List[int]:
        """
        Улучшенный резервный поиск с поддержкой синонимов
        """
        logger.info(f"Используется улучшенный резервный поиск для запроса: '{query}'")
        
        # Если это уже расширенный запрос, используем его как есть
        if len(query.split()) > 3:
            search_terms = query.lower().split()
        else:
            # Иначе расширяем запрос
            expanded = self.expand_search_query(query)
            search_terms = expanded.lower().split()
        
        # Создаем Q объект для поиска по всем терминам
        q_objects = Q()
        
        for term in search_terms:
            if len(term) > 2:  # Игнорируем слишком короткие слова
                q_objects |= (
                    Q(name__icontains=term) | 
                    Q(article__icontains=term) |
                    Q(description__icontains=term)
                )
        
        if q_objects:
            products = Product.objects.filter(q_objects).values_list('id', flat=True)
            result = list(products)
            logger.info(f"Улучшенный fallback поиск нашел {len(result)} товаров")
            return result
        else:
            logger.info("Улучшенный fallback поиск не нашел товаров")
            return []
    
    def smart_search(self, query: str) -> List[Product]:
        """
        Главный метод для выполнения улучшенного умного поиска
        """
        if not query or not query.strip():
            return Product.objects.none()
        
        query = query.strip()
        logger.info(f"Выполняется улучшенный умный поиск для запроса: '{query}'")
        
        # Анализируем каталог для поиска связей (кешируем результат)
        if not hasattr(self, '_catalog_analysis'):
            self._catalog_analysis = self.analyze_product_catalog()
        
        # Получаем ID релевантных товаров
        product_ids = self.search_with_chatgpt(query)
        
        if not product_ids:
            logger.info("Умный поиск не нашел товаров")
            return Product.objects.none()
        
        # Получаем товары по найденным ID с сохранением порядка
        products = Product.objects.filter(id__in=product_ids)
        
        # Сортируем в том же порядке, что вернул ChatGPT (более релевантные первыми)
        product_dict = {p.id: p for p in products}
        ordered_products = [product_dict[pid] for pid in product_ids if pid in product_dict]
        
        logger.info(f"Итоговый результат умного поиска: {len(ordered_products)} товаров")
        return ordered_products

# Создаем глобальный экземпляр сервиса
smart_search_service = SmartSearchService()