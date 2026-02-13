#!/usr/bin/env python3
"""
Очистка и восстановление транскрибаций аудио.

Исправляет:
- Отсутствие знаков препинания
- OCR-ошибки (искаженные слова)
- Разрывы текста
- Артефакты транскрибации

Использование:
    python clean_transcription.py --input transcriptions_raw --output transcriptions_clean
"""

import re
import argparse
from pathlib import Path
from typing import List, Dict, Any


class TranscriptionCleaner:
    """
    Класс для очистки и восстановления транскрибированного текста
    """
    
    def __init__(self):
        # Словарь типичных ошибок OCR/распознавания речи
        self.common_errors = {
            # Звуковые артефакты
            r'\[музыка\]': '',
            r'\[шум\]': '',
            r'\[нрзб\]': '',
            r'\(звук\)': '',
            r'\(аплодисменты\)': '',
            r'\(смех\)': '',
            r'\.\.\.': ' ',  # Многоточия заменяем на пробел
            r'  +': ' ',  # Множественные пробелы
        }
        
        # Словарь для исправления слов
        self.word_fixes = {
            'деньжата': 'деньги',
            'вообщем': 'в общем',
            'вобщем': 'в общем',
            'короче': 'короче',
            'типа': 'типа',
            'как бы': 'как бы',
            'ну типа': 'ну типа',
            'кста': 'кстати',
            'плиз': 'пожалуйста',
            'спс': 'спасибо',
            'прив': 'привет',
            'пон': 'понятно',
            'не пон': 'не понятно',
            'чет': 'что-то',
            'короч': 'короче',
        }
    
    def _remove_artifacts(self, text: str) -> str:
        """Удаление артефактов транскрибации"""
        for pattern, replacement in self.common_errors.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text.strip()
    
    def _fix_words(self, text: str) -> str:
        """Исправление отдельных слов"""
        words = text.split()
        fixed_words = []
        
        for word in words:
            # Очищаем от пунктуации для проверки
            clean = word.lower().strip('.,!?;:')
            if clean in self.word_fixes:
                # Сохраняем регистр первой буквы
                if word[0].isupper():
                    fixed = self.word_fixes[clean].capitalize()
                else:
                    fixed = self.word_fixes[clean]
                # Восстанавливаем пунктуацию
                if word[-1] in '.,!?;:':
                    fixed += word[-1]
                fixed_words.append(fixed)
            else:
                fixed_words.append(word)
        
        return ' '.join(fixed_words)
    
    def _add_punctuation(self, text: str) -> str:
        """Восстановление пунктуации"""
        # Разбиваем на предложения по длине и союзам
        words = text.split()
        if not words:
            return text
        
        sentences = []
        current = []
        
        for i, word in enumerate(words):
            current.append(word)
            
            # Признаки конца предложения
            if i < len(words) - 1:
                next_word = words[i + 1].lower()
                
                # Конец перед союзом (начало нового предложения)
                if next_word in ['а', 'но', 'и', 'или', 'что', 'где', 'когда', 'почему']:
                    if len(current) >= 3:
                        sentences.append(' '.join(current))
                        current = []
                
                # Конец перед ответом
                if next_word in ['да', 'нет', 'конечно'] and len(current) >= 2:
                    sentences.append(' '.join(current))
                    current = []
        
        if current:
            sentences.append(' '.join(current))
        
        # Добавляем знаки препинания
        result = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            
            lower = sent.lower()
            
            # Вопросительное
            if any(w in lower for w in ['что', 'где', 'когда', 'почему', 'зачем', 'кто', 'как', 'какой', 'который']):
                if not sent.endswith('?'):
                    sent += '?'
            # Восклицательное
            elif any(w in lower for w in ['вау', 'ого', 'круто', 'супер', 'боже', 'черт', 'ого']):
                if not sent.endswith('!'):
                    sent += '!'
            # Обычное
            else:
                if not sent[-1] in '.!?':
                    sent += '.'
            
            result.append(sent)
        
        return ' '.join(result)
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """Разбиение на абзацы по смысловым блокам"""
        # Разбиваем по пустым строкам или длинным паузам
        paragraphs = re.split(r'\n\s*\n|\n{2,}', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def process_file(self, input_path: Path, output_path: Path):
        """Обработка одного файла"""
        print(f"🎙️ Обработка: {input_path.name}")
        
        # Читаем
        text = input_path.read_text(encoding='utf-8')
        original_len = len(text)
        
        # Обрабатываем
        text = self._remove_artifacts(text)
        text = self._fix_words(text)
        
        # Разбиваем на абзацы и обрабатываем каждый
        paragraphs = self._split_paragraphs(text)
        processed = []
        
        for i, para in enumerate(paragraphs):
            print(f"  📄 Абзац {i+1}/{len(paragraphs)}")
            para = self._add_punctuation(para)
            processed.append(para)
        
        # Собираем
        final_text = '\n\n'.join(processed)
        
        # Добавляем метаинформацию
        header = f"""# Очищенная транскрибация
## Исходный файл: {input_path.name}
## Абзацев: {len(paragraphs)}
## Символов: {original_len} → {len(final_text)}

---

"""
        
        full_text = header + final_text
        
        # Сохраняем
        output_path.write_text(full_text, encoding='utf-8')
        
        print(f"  ✅ Сохранено: {output_path}")
        return len(paragraphs)
    
    def process_directory(self, input_dir: Path, output_dir: Path):
        """Обработка всей папки"""
        output_dir.mkdir(exist_ok=True)
        
        txt_files = list(input_dir.glob('*.txt'))
        if not txt_files:
            print(f"⚠️  Нет .txt файлов в {input_dir}")
            return
        
        print(f"\n🎯 Найдено файлов: {len(txt_files)}\n")
        
        total_paragraphs = 0
        for i, txt_file in enumerate(txt_files, 1):
            print(f"\n[{i}/{len(txt_files)}]")
            output_file = output_dir / f"clean_{txt_file.name}"
            try:
                paras = self.process_file(txt_file, output_file)
                total_paragraphs += paras
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
        
        print("\n" + "="*50)
        print("📊 ИТОГИ:")
        print(f"  Файлов: {len(txt_files)}")
        print(f"  Абзацев: {total_paragraphs}")
        print(f"  Сохранено в: {output_dir}")
        print("="*50 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Очистка транскрибаций аудио')
    parser.add_argument('--input', '-i', default='transcriptions_raw',
                       help='Папка с сырыми транскрибациями')
    parser.add_argument('--output', '-o', default='transcriptions_clean',
                       help='Папка для очищенных файлов')
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    if not input_dir.exists():
        print(f"❌ Папка не найдена: {input_dir}")
        print("Создайте папку и положите туда .txt файлы")
        return
    
    cleaner = TranscriptionCleaner()
    cleaner.process_directory(input_dir, output_dir)
    
    print("✅ Готово! Теперь можно размечать техники Kimi.")


if __name__ == "__main__":
    main()