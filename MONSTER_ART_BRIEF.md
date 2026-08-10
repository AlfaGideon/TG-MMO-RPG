# Боевые монстры — направление иллюстраций

> Этот документ намеренно отделён от `admin/static/pets/`: сохранённые круглые
> слаймы — будущие питомцы и не должны использоваться на экране боя.

## Обязательная композиция

- **Одна картинка = один монстр.** Никаких 3×3, sprite sheet, коллажей и подписей.
- Квадрат 1:1, рекомендуемый исходник 1024×1024; монстр показан **в полный рост**.
- Читаемый силуэт вида важнее слизевой фактуры: оборотень сначала выглядит
  оборотнем, скелет — скелетом, зомби — человеком-зомби.
- Слайм — это **материал тела**, а не базовый круглый персонаж с приклеенными
  ушами, костями или доспехом.
- Тёмное фэнтези, серьёзный и опасный противник, без chibi/cute/mascot эстетики.
- Тёмный атмосферный фон, контровой свет, свободные поля вокруг конечностей,
  без текста, рамок, UI и логотипов.

## Как должна работать слизь

- Полупрозрачная или мутная вязкая масса формирует мышцы, кожу, сухожилия и
  суставы полноценного тела.
- Внутри видны пузырьки, потоки, включения, повреждения и слабое свечение.
- Скелет: гуманоид в полный рост, но «кости» сформированы плотной бледной
  слизью; между ними тянутся прозрачные вязкие нити.
- Зомби: гуманоид в полный рост, разложившаяся плоть заменена болотной слизью,
  из разрывов стекает вязкая масса.
- Оборотень/ворг: полноценный высокий зверь на лапах, мускулатура и шерстяной
  силуэт сформированы тёмной прозрачной слизью, внутри светятся жилы.
- Доспехи, оружие, ткань и украшения могут быть твёрдыми; само тело под ними —
  слизевое и анатомически сформированное.

## Базовый prompt

```text
Single full-body dark fantasy [CREATURE], standing in an intimidating combat
pose. The creature keeps the complete anatomical silhouette of a [CREATURE],
but its flesh, muscles, skin and internal structure are formed from translucent
viscous slime with bubbles, flowing strands and subtle inner glow. It is NOT a
round blob and NOT a cute slime with attached costume parts. Serious terrifying
RPG enemy, realistic proportions, head-to-toe visible, cinematic rim lighting,
dark atmospheric environment, centered composition, square 1:1, no text, no
frame, no UI, no collage, one creature only.
```

### Negative prompt / запреты

```text
cute, chibi, mascot, round blob, ball-shaped slime, sticker, pet, cropped body,
portrait close-up, multiple creatures, grid, contact sheet, sprite sheet, text,
logo, border, cartoon accessories glued onto a slime
```

## Первая очередь боевых портретов

1. Болотный зомби — гуманоид из болотной гнилой слизи.
2. Лесной ворг — полноценный зверь/оборотень из чёрной прозрачной слизи.
3. Скелет-воин — полный гуманоидный скелет из костяной слизи с мечом.
4. Гнолл-грабитель — гиеноподобный воин со слизевым телом.
5. Пещерный тролль — массивный двуногий тролль из каменистой слизи.
6. Теневой призрак — вытянутый гуманоид из дымной фиолетовой слизи.
7. Могильный страж — рыцарь в полный рост, тело под бронёй из мёртвой слизи.
8. Гарпия-падальщица — полноценная крылатая гарпия со слизевой анатомией.
9. Топяной змей — длинный змей, целиком сформированный болотной слизью.
10. Пожиратель миров — огромный финальный гуманоидный/демонический босс из
    бездонной слизи, не шар и не бесформенная лужа.

## Готовые серии

Утверждённое направление применено к 37 одиночным портретам:

- `garbage_rat.jpg`, `swamp_zombie.jpg`, `forest_worg.jpg`
- `weaver_spider.jpg`, `trickster_leshy.jpg`, `rotten_boar.jpg`
- `skeleton_warrior.jpg`, `gnoll_raider.jpg`, `rusty_knight.jpg`
- `marauder_marksman.jpg`, `war_hound.jpg`, `cave_troll.jpg`
- `shadow_ghost.jpg`, `bone_priest.jpg`, `bone_wanderer.jpg`
- `grave_guardian.jpg`, `carrion_harpy.jpg`, `bog_serpent.jpg`
- `ice_scavenger.jpg`, `northern_buzzard.jpg`, `snow_wolf.jpg`
- `dark_tracker.jpg`, `ash_warlock.jpg`, `rotting_giant.jpg`
- `mire_golem.jpg`, `abyss_cultist.jpg`, `world_devourer.jpg`
- `grave_worm.jpg`, `banshee_mourner.jpg`, `bone_golem.jpg`
- `abyss_spawn.jpg`, `rift_guardian.jpg`, `rock_predator.jpg`
- `ash_wolf.jpg`, `frozen_zombie.jpg`, `mountain_troll.jpg`
- `stone_skin_guardian.jpg`

Они лежат в `admin/static/mobs/`. Следующая серия должна точно продолжать
этот стиль. Один портрет мародёра используется и для стрелка, и для
разбойника с большой дороги до появления отдельного варианта.
