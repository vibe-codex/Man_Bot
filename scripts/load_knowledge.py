#!/usr/bin/env python3
"""
Скрипт загрузки техник из Markdown файлов в векторную базу PostgreSQL.

Использование:
    python load_knowledge.py --source ../KIMI_OUTPUT --provider google

Требования:
    - Установленный PostgreSQL с pgvector
    - Переменные окружения в .env файле
    - Ключ API (Google/OpenAI/DeepSeek)
"""

import os
import sys
import re
import json
import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import yaml
import asyncpg
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


@dataclass
class KnowledgeUnit:
    """Структура единицы знания"""
    ku_id: str
    title: str
    content: str
    yaml_data: Dict[str, Any]
    level: str
    user_level_fit: List[str]
    stage: List[str]
    channel: List[str]
    goal: List[str]
    style: List[str]
    riskiness: int
    embedding: Optional[List[float]] = None


class EmbeddingGenerator:
    """Генератор эмбеддингов через разные провайдеры"""
    
    def __init__(self, provider: str = "google"):
        self.provider = provider
        self.dimension = int(os.getenv("EMBED_DIMENSION", "768"))
        
        if provider == "google":
            self._init_google()
        elif provider == "openai":
            self._init_openai()
        elif provider == "deepseek":
            self._init_deepseek()
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _init_google(self):
        """Инициализация Google Generative AI"""
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        genai.configure(api_key=api_key)
        self.model = os.getenv("EMBED_MODEL", "models/embedding-001")
        self.client = genai
    
    def _init_openai(self):
        """Инициализация OpenAI"""
        import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        openai.api_key = api_key
        self.model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
        self.client = openai
    
    def _init_deepseek(self):
        """Инициализация DeepSeek"""
        # DeepSeek использует OpenAI-совместимый API
        import openai
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment")
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = os.getenv("EMBED_MODEL", "deepseek-embedding")
    
    async def generate(self, text: str) -> List[float]:
        """Генерация эмбеддинга для текста"""
        try:
            if self.provider == "google":
                result = self.client.embed_content(
                    model=self.model,
                    content=text,
                    task_type="retrieval_document"
                )
                return result['embedding']
            
            elif self.provider in ["openai", "deepseek"]:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text
                )
                return response.data[0].embedding
                
        except Exception as e:
            print(f"⚠️  Ошибка генерации эмбеддинга: {e}")
            # Возвращаем нулевой вектор как fallback
            return [0.0] * self.dimension


class MarkdownParser:
    """Парсер Markdown файлов с YAML frontmatter"""
    
    @staticmethod
    def parse_file(filepath: Path) -> Optional[KnowledgeUnit]:
        """Парсит один .md файл"""
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Разделяем frontmatter и контент
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    yaml_content = parts[1].strip()
                    markdown_content = parts[2].strip()
                else:
                    return None
            else:
                return None
            
            # Парсим YAML
            try:
                yaml_data = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                print(f"⚠️  YAML ошибка в {filepath.name}: {e}")
                return None
            
            # Извлекаем поля
            ku_id = yaml_data.get('id', filepath.stem)
            title = yaml_data.get('title', ku_id)
            level = yaml_data.get('Level', 'база')
            user_level_fit = yaml_data.get('UserLevelFit', ['новичок'])
            stage = yaml_data.get('Stage', [])
            channel = yaml_data.get('Channel', [])
            goal = yaml_data.get('Goal', [])
            style = yaml_data.get('Style', [])
            riskiness = yaml_data.get('Riskiness', 1)
            
            # Очищаем контент от YAML для эмбеддинга
            clean_content = markdown_content
            # Удаляем markdown-разметку для лучшего эмбеддинга
            clean_content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_content)  # ссылки
            clean_content = re.sub(r'[#*_`]', '', clean_content)  # markdown символы
            
            return KnowledgeUnit(
                ku_id=ku_id,
                title=title,
                content=markdown_content,
                yaml_data=yaml_data,
                level=level,
                user_level_fit=user_level_fit if isinstance(user_level_fit, list) else [user_level_fit],
                stage=stage if isinstance(stage, list) else [stage],
                channel=channel if isinstance(channel, list) else [channel],
                goal=goal if isinstance(goal, list) else [goal],
                style=style if isinstance(style, list) else [style],
                riskiness=riskiness
            )
            
        except Exception as e:
            print(f"⚠️  Ошибка парсинга {filepath}: {e}")
            return None


class DatabaseLoader:
    """Загрузчик в PostgreSQL"""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn = None
    
    async def connect(self):
        """Подключение к базе"""
        self.conn = await asyncpg.connect(self.dsn)
        print("✅ Подключено к PostgreSQL")
    
    async def close(self):
        """Закрытие соединения"""
        if self.conn:
            await self.conn.close()
    
    async def insert_knowledge_unit(self, ku: KnowledgeUnit) -> bool:
        """Вставка одной единицы знания"""
        try:
            await self.conn.execute(
                """
                INSERT INTO knowledge_units 
                (ku_id, title, content, yaml, level, user_level_fit, stage, channel, goal, style, riskiness, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::vector)
                ON CONFLICT (ku_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    yaml = EXCLUDED.yaml,
                    level = EXCLUDED.level,
                    user_level_fit = EXCLUDED.user_level_fit,
                    stage = EXCLUDED.stage,
                    channel = EXCLUDED.channel,
                    goal = EXCLUDED.goal,
                    style = EXCLUDED.style,
                    riskiness = EXCLUDED.riskiness,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                ku.ku_id,
                ku.title,
                ku.content,
                json.dumps(ku.yaml_data, ensure_ascii=False),
                ku.level,
                ku.user_level_fit,
                ku.stage,
                ku.channel,
                ku.goal,
                ku.style,
                ku.riskiness,
                ku.embedding
            )
            return True
        except Exception as e:
            print(f"⚠️  Ошибка вставки {ku.ku_id}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, int]:
        """Статистика базы"""
        count = await self.conn.fetchval("SELECT COUNT(*) FROM knowledge_units")
        return {"total_units": count}


async def main():
    parser = argparse.ArgumentParser(description='Загрузка техник в векторную базу')
    parser.add_argument('--source', '-s', default='../KIMI_OUTPUT',
                       help='Папка с .md файлами (default: ../KIMI_OUTPUT)')
    parser.add_argument('--provider', '-p', default='google',
                       choices=['google', 'openai', 'deepseek'],
                       help='Провайдер эмбеддингов (default: google)')
    parser.add_argument('--dsn', '-d', default=os.getenv('DB_DSN'),
                       help='PostgreSQL connection string')
    
    args = parser.parse_args()
    
    if not args.dsn:
        print("❌ Ошибка: Не указан DSN базы данных")
        print("Используйте --dsn или установите переменную окружения DB_DSN")
        sys.exit(1)
    
    source_path = Path(args.source)
    if not source_path.exists():
        print(f"❌ Ошибка: Папка {source_path} не существует")
        sys.exit(1)
    
    print(f"🚀 Загрузка техник из {source_path}")
    print(f"🔧 Провайдер эмбеддингов: {args.provider}")
    print()
    
    # Инициализация компонентов
    print("📡 Подключение к базе данных...")
    db = DatabaseLoader(args.dsn)
    await db.connect()
    
    print(f"🤖 Инициализация {args.provider}...")
    try:
        embedder = EmbeddingGenerator(args.provider)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Сканирование файлов
    md_files = list(source_path.glob("*.md"))
    print(f"📚 Найдено файлов: {len(md_files)}")
    print()
    
    # Парсинг и загрузка
    successful = 0
    failed = 0
    
    for i, filepath in enumerate(md_files, 1):
        print(f"[{i}/{len(md_files)}] Обработка {filepath.name}...", end=" ")
        
        # Парсим
        ku = MarkdownParser.parse_file(filepath)
        if not ku:
            print("❌ Парсинг не удался")
            failed += 1
            continue
        
        # Генерируем эмбеддинг
        text_for_embedding = f"{ku.title}\n{ku.content[:1000]}"  # Берём начало контента
        ku.embedding = await embedder.generate(text_for_embedding)
        
        # Загружаем в базу
        if await db.insert_knowledge_unit(ku):
            print(f"✅ {ku.ku_id}")
            successful += 1
        else:
            print("❌ Ошибка загрузки")
            failed += 1
    
    # Итоги
    print()
    print("=" * 50)
    print("📊 ИТОГИ ЗАГРУЗКИ:")
    print(f"   ✅ Успешно: {successful}")
    print(f"   ❌ Ошибок: {failed}")
    
    stats = await db.get_stats()
    print(f"   📦 Всего в базе: {stats['total_units']} техник")
    print("=" * 50)
    
    await db.close()
    print()
    print("🎉 Готово! Теперь можно запускать бота.")


if __name__ == "__main__":
    asyncio.run(main())