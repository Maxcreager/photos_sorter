import os
import argparse
from PIL import Image
import shutil
from datetime import datetime
import re
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# --- Fonctions Existantes ---
def extraire_infos_exif(chemin_fichier):
    try:
        image = Image.open(chemin_fichier)
        info_exif = image.getexif()
        date_prise = info_exif.get(36867)  # DateTimeOriginal
        if date_prise:
            return datetime.strptime(date_prise, '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        logging.error(f"Erreur EXIF pour {chemin_fichier} : {e}")
    return None

def extraire_date_nom_fichier(nom_fichier):
    match = re.search(r'(IMG|VID)_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', nom_fichier)
    if match:
        try:
            date_str = f"{match.group(2)}-{match.group(3)}-{match.group(4)} {match.group(5)}:{match.group(6)}:{match.group(7)}"
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            logging.error(f"Erreur de conversion pour {nom_fichier} : {e}")
    return None

def formater_nom_fichier(date_prise, nom_fichier_original, format_nom='%Y_%m_%d_%H%M%S'):
    extension = os.path.splitext(nom_fichier_original)[1]
    return f"{date_prise.strftime(format_nom)}{extension}" if date_prise else None

def gerer_doublons(chemin, dossier_cible):
    if os.path.exists(chemin):
        base, extension = os.path.splitext(chemin)
        compteur = 1
        nouveau_chemin = f"{base}_{compteur}{extension}"
        while os.path.exists(nouveau_chemin):
            compteur += 1
            nouveau_chemin = f"{base}_{compteur}{extension}"
        return nouveau_chemin
    return chemin

def trier_photos(dossier_entree, dossier_sortie, format_nom='%Y_%m_%d_%H%M%S', dry_run=False, progress_callback=None):
    os.makedirs(dossier_sortie, exist_ok=True)
    dossier_autres = os.path.join(dossier_sortie, "Autres")
    os.makedirs(dossier_autres, exist_ok=True)
    
    # Collecter tous les fichiers à traiter
    fichiers = []
    for racine, _, fichiers_fichiers in os.walk(dossier_entree):
        for fichier in fichiers_fichiers:
            fichiers.append(os.path.join(racine, fichier))
    
    total_fichiers = len(fichiers)
    fichiers_deplaces = 0
    fichiers_autres = 0
    erreurs = 0

    for idx, chemin_complet in enumerate(fichiers, start=1):
        fichier = os.path.basename(chemin_complet)
        date_prise = extraire_infos_exif(chemin_complet) or extraire_date_nom_fichier(fichier)
        
        if date_prise:
            dossier_cible = os.path.join(dossier_sortie, str(date_prise.year), f"{date_prise.month:02}")
            if not dry_run:
                os.makedirs(dossier_cible, exist_ok=True)
            nouveau_nom = formater_nom_fichier(date_prise, fichier, format_nom)
            chemin_nouveau_fichier = os.path.join(dossier_cible, nouveau_nom)
            chemin_nouveau_fichier = gerer_doublons(chemin_nouveau_fichier, dossier_cible)
            
            if dry_run:
                logging.info(f"Simulé : déplacer {chemin_complet} vers {chemin_nouveau_fichier}")
            else:
                try:
                    shutil.move(chemin_complet, chemin_nouveau_fichier)
                    fichiers_deplaces += 1
                    logging.info(f"Déplacé : {chemin_complet} vers {chemin_nouveau_fichier}")
                except Exception as e:
                    logging.error(f"Erreur lors du déplacement de {chemin_complet} : {e}")
                    erreurs += 1
        else:
            chemin_autres = os.path.join(dossier_autres, fichier)
            if dry_run:
                logging.info(f"Simulé : déplacer {chemin_complet} vers {chemin_autres}")
            else:
                try:
                    shutil.move(chemin_complet, chemin_autres)
                    fichiers_autres += 1
                    logging.info(f"Déplacé dans 'Autres' : {chemin_complet}")
                except Exception as e:
                    logging.error(f"Erreur lors du déplacement de {chemin_complet} vers 'Autres' : {e}")
                    erreurs += 1

        # Mettre à jour la progression
        if progress_callback:
            progress_callback(idx, total_fichiers)

    rapport = (
        f"Total de fichiers traités : {total_fichiers}\n"
        f"Fichiers déplacés : {fichiers_deplaces}\n"
        f"Fichiers dans 'Autres' : {fichiers_autres}\n"
        f"Erreurs : {erreurs}\n"
    )
    logging.info("Tri terminé.\n" + rapport)
    return rapport

# --- Configuration du Logging ---
def configurer_logging():
    logging.basicConfig(
        filename='tri_photos.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

# --- Interface Graphique avec Tkinter ---
class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tri de Photos")
        self.geometry("600x500")
        self.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        # Dossier d'entrée
        self.label_input = ttk.Label(self, text="Dossier d'entrée:")
        self.label_input.pack(pady=10)
        
        self.frame_input = ttk.Frame(self)
        self.frame_input.pack(pady=5, padx=20, fill='x')
        
        self.entry_input = ttk.Entry(self.frame_input)
        self.entry_input.pack(side='left', fill='x', expand=True)
        
        self.button_browse_input = ttk.Button(self.frame_input, text="Parcourir", command=self.browse_input)
        self.button_browse_input.pack(side='left', padx=5)
        
        # Dossier de sortie
        self.label_output = ttk.Label(self, text="Dossier de sortie:")
        self.label_output.pack(pady=10)
        
        self.frame_output = ttk.Frame(self)
        self.frame_output.pack(pady=5, padx=20, fill='x')
        
        self.entry_output = ttk.Entry(self.frame_output)
        self.entry_output.pack(side='left', fill='x', expand=True)
        
        self.button_browse_output = ttk.Button(self.frame_output, text="Parcourir", command=self.browse_output)
        self.button_browse_output.pack(side='left', padx=5)
        
        # Format nom
        self.label_format = ttk.Label(self, text="Format de nom (optionnel):")
        self.label_format.pack(pady=10)
        
        self.entry_format = ttk.Entry(self)
        self.entry_format.insert(0, "%Y_%m_%d_%H%M%S")
        self.entry_format.pack(pady=5, padx=20, fill='x')
        
        # Options supplémentaires
        self.var_dry_run = tk.BooleanVar()
        self.check_dry_run = ttk.Checkbutton(self, text="Mode Aperçu (Dry Run)", variable=self.var_dry_run)
        self.check_dry_run.pack(pady=10)
        
        # Bouton de démarrage
        self.button_start = ttk.Button(self, text="Démarrer le Tri", command=self.start_sorting)
        self.button_start.pack(pady=10)
        
        # Barre de progression
        self.progress = ttk.Progressbar(self, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=10)
        
        # Zone de rapport
        self.label_report = ttk.Label(self, text="Rapport:")
        self.label_report.pack(pady=10)
        
        self.text_report = tk.Text(self, height=10, state='disabled')
        self.text_report.pack(pady=5, padx=20, fill='both', expand=True)

    def browse_input(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.entry_input.delete(0, tk.END)
            self.entry_input.insert(0, folder_selected)

    def browse_output(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, folder_selected)

    def start_sorting(self):
        dossier_entree = self.entry_input.get()
        dossier_sortie = self.entry_output.get()
        format_nom = self.entry_format.get()
        dry_run = self.var_dry_run.get()
        
        if not dossier_entree:
            messagebox.showerror("Erreur", "Veuillez sélectionner un dossier d'entrée.")
            return
        if not dossier_sortie:
            messagebox.showerror("Erreur", "Veuillez sélectionner un dossier de sortie.")
            return
        
        # Désactiver le bouton pour éviter les clics multiples
        self.button_start.config(state='disabled')
        self.progress['value'] = 0
        self.text_report.configure(state='normal')
        self.text_report.delete(1.0, tk.END)
        self.text_report.configure(state='disabled')

        # Lancer le tri dans un thread
        threading.Thread(target=self.run_sorting, args=(dossier_entree, dossier_sortie, format_nom, dry_run)).start()

    def run_sorting(self, dossier_entree, dossier_sortie, format_nom, dry_run):
        def update_progress(current, total):
            progress_percent = (current / total) * 100
            self.progress['value'] = progress_percent
            self.update_idletasks()

        rapport = trier_photos(dossier_entree, dossier_sortie, format_nom, dry_run, progress_callback=update_progress)
        self.afficher_rapport(rapport)
        messagebox.showinfo("Terminé", "Le tri des photos est terminé.")
        self.button_start.config(state='normal')

    def afficher_rapport(self, texte):
        self.text_report.configure(state='normal')
        self.text_report.delete(1.0, tk.END)
        self.text_report.insert(tk.END, texte)
        self.text_report.configure(state='disabled')

# --- Main ---
if __name__ == "__main__":
    configurer_logging()
    app = Application()
    app.mainloop()
