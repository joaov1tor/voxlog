---
cssclasses: []
---
# 🎙️ Central de Gravações

## Últimos momentos (timeline)
```dataview
TABLE tipo, origem, assunto, duracao_min as "min", resumido_por
FROM "🎙️ Gravações"
WHERE tipo
SORT data DESC, hora_inicio DESC
LIMIT 50
```

## Por assunto
```dataview
TABLE rows.file.link as Notas, length(rows) as Qtd
FROM "🎙️ Gravações"
WHERE tipo
GROUP BY assunto
SORT length(rows) DESC
```

## Só reuniões
```dataview
LIST
FROM "🎙️ Gravações"
WHERE tipo = "reuniao"
SORT data DESC
```

## Pendentes de reprocessar (sem resumo)
```dataview
LIST
FROM "🎙️ Gravações"
WHERE resumido_por = "nenhum"
```
