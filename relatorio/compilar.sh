#!/usr/bin/env bash
# Compila o relatório LaTeX em PDF (ABNT via abntex2)
# Requer: texlive-full  (sudo apt-get install -y texlive-full)
# Uso: bash compilar.sh

set -e
cd "$(dirname "$0")"

echo "=== Compilação 1/2 ==="
pdflatex -interaction=nonstopmode relatorio.tex

echo "=== Compilação 2/2 (resolve referências cruzadas) ==="
pdflatex -interaction=nonstopmode relatorio.tex

echo ""
echo "✓ PDF gerado: $(pwd)/relatorio.pdf"

# Limpa arquivos auxiliares
rm -f relatorio.aux relatorio.log relatorio.out relatorio.toc \
       relatorio.lof relatorio.lot relatorio.lol relatorio.bbl \
       relatorio.blg relatorio.bcf relatorio.run.xml
