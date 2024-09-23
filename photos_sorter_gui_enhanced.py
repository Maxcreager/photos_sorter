import os
import shutil
from PIL import Image
from datetime import datetime
import re
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import csv
from concurrent.futures import ThreadPoolExecutor
import json

# --- Fonctions Existantes et Améliorées ---
SUPPORTED_IMAGE_TYPES = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif')
SUPPORTED_VIDEO_TYPES = ('.mp4', '.mov', '.avi')
SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES + SUPPORTED_VIDEO_TYPES

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

def filtrer_fichier(chemin_fichier, min_taille, min_resolution):
    taille = os.path.getsize(chemin_fichier) / (1024 * 1024)  # Taille en Mo
    if taille < min_taille:
        return False
    if min_resolution:
        try:
            largeur_min, hauteur_min = map(int, min_resolution.lower().split('x'))
            with Image.open(chemin_fichier) as img:
                largeur, hauteur = img.size
                if largeur < largeur_min or hauteur < hauteur_min:
                    return False
        except Exception as e:
            logging.error(f"Erreur lors de la vérification de la résolution pour {chemin_fichier} : {e}")
            return False
    return True

def optimiser_image(chemin_fichier, chemin_destination, taille_max=(1920, 1080)):
    try:
        with Image.open(chemin_fichier) as img:
            img.thumbnail(taille_max)
            img.save(chemin_destination, optimize=True, quality=85)
        logging.info(f"Optimisé : {chemin_fichier} vers {chemin_destination}")
    except Exception as e:
        logging.error(f"Erreur lors de l'optimisation de {chemin_fichier} : {e}")

def exporter_exif(dossier_sortie, fichier_csv):
    with open(fichier_csv, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Nom Fichier', 'Date Prise', 'Appareil', 'GPS']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for racine, _, fichiers in os.walk(dossier_sortie):
            for fichier in fichiers:
                chemin = os.path.join(racine, fichier)
                exif = extraire_infos_exif(chemin)
                appareil = "N/A"
                gps = "N/A"
                try:
                    image = Image.open(chemin)
                    info_exif = image.getexif()
                    appareil = info_exif.get(272, "N/A")  # Model
                    # Extraction GPS simplifiée
                    gps_info = info_exif.get(34853)
                    if gps_info:
                        gps = str(gps_info)
                except Exception as e:
                    logging.error(f"Erreur lors de l'extraction des métadonnées pour {chemin} : {e}")
                writer.writerow({
                    'Nom Fichier': fichier,
                    'Date Prise': exif.strftime('%Y-%m-%d %H:%M:%S') if exif else '',
                    'Appareil': appareil,
                    'GPS': gps
                })

def trier_photos(dossier_entree, dossier_sortie, format_nom='%Y_%m_%d_%H%M%S', dry_run=False, progress_callback=None,
                min_taille=0, min_resolution=None, exporter_csv=False, optimiser=False):
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

    # Utilisation de ThreadPoolExecutor pour le traitement en parallèle
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for idx, chemin_complet in enumerate(fichiers, start=1):
            futures.append(executor.submit(process_file, chemin_complet, dossier_sortie, format_nom, dry_run,
                                           min_taille, min_resolution, optimiser))
        
        for idx, future in enumerate(futures, start=1):
            result = future.result()
            if result == 'deplace':
                fichiers_deplaces += 1
            elif result == 'autres':
                fichiers_autres += 1
            elif result == 'erreur':
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
    
    if exporter_csv:
        fichier_csv = os.path.join(dossier_sortie, 'exif_data.csv')
        exporter_exif(dossier_sortie, fichier_csv)
        rapport += f"Les données EXIF ont été exportées vers : {fichier_csv}\n"
    
    return rapport

def process_file(chemin_complet, dossier_sortie, format_nom, dry_run, min_taille, min_resolution, optimiser):
    fichier = os.path.basename(chemin_complet)
    
    # Filtrage
    if not filtrer_fichier(chemin_complet, min_taille, min_resolution):
        logging.info(f"Filtré : {chemin_complet}")
        return 'filtré'
    
    # Vérifier le type de fichier supporté
    _, extension = os.path.splitext(fichier)
    if extension.lower() not in SUPPORTED_TYPES:
        logging.info(f"Type de fichier non supporté : {chemin_complet}")
        return 'filtré'
    
    date_prise = extraire_infos_exif(chemin_complet) or extraire_date_nom_fichier(fichier)
    
    if date_prise:
        dossier_cible = os.path.join(dossier_sortie, str(date_prise.year), f"{date_prise.month:02}")
        if not dry_run:
            os.makedirs(dossier_cible, exist_ok=True)
        nouveau_nom = formater_nom_fichier(date_prise, fichier, format_nom)
        chemin_nouveau_fichier = os.path.join(dossier_cible, nouveau_nom)
        chemin_nouveau_fichier = gerer_doublons(chemin_nouveau_fichier, dossier_cible)
        
        if optimiser and extension.lower() in SUPPORTED_IMAGE_TYPES:
            # Optimiser l'image avant de la déplacer
            chemin_temp = chemin_nouveau_fichier + ".tmp"
            optimiser_image(chemin_complet, chemin_temp)
            chemin_nouveau_fichier = chemin_temp
        
        if dry_run:
            logging.info(f"Simulé : déplacer {chemin_complet} vers {chemin_nouveau_fichier}")
        else:
            try:
                shutil.move(chemin_complet, chemin_nouveau_fichier)
                logging.info(f"Déplacé : {chemin_complet} vers {chemin_nouveau_fichier}")
                return 'deplace'
            except Exception as e:
                logging.error(f"Erreur lors du déplacement de {chemin_complet} : {e}")
                return 'erreur'
    else:
        chemin_autres = os.path.join(dossier_sortie, "Autres", fichier)
        if dry_run:
            logging.info(f"Simulé : déplacer {chemin_complet} vers {chemin_autres}")
        else:
            try:
                shutil.move(chemin_complet, chemin_autres)
                logging.info(f"Déplacé dans 'Autres' : {chemin_complet}")
                return 'autres'
            except Exception as e:
                logging.error(f"Erreur lors du déplacement de {chemin_complet} vers 'Autres' : {e}")
                return 'erreur'

# --- Undo / Restauration des Fichiers ---
HISTORY_FILE = 'historique_moves.json'

def enregistrer_mouvement(original, destination):
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            historique = json.load(f)
    else:
        historique = []
    
    historique.append({'original': original, 'destination': destination})
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(historique, f, indent=4)

def restaurer_fichiers():
    if not os.path.exists(HISTORY_FILE):
        logging.info("Aucun historique de mouvements trouvé.")
        return "Aucun historique de mouvements trouvé."
    
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        historique = json.load(f)
    
    erreurs = 0
    for mouvement in reversed(historique):
        original = mouvement['original']
        destination = mouvement['destination']
        try:
            shutil.move(destination, original)
            logging.info(f"Restauré : {destination} vers {original}")
        except Exception as e:
            logging.error(f"Erreur lors de la restauration de {destination} : {e}")
            erreurs += 1
    
    # Effacer l'historique après restauration
    os.remove(HISTORY_FILE)
    
    if erreurs == 0:
        return "Tous les fichiers ont été restaurés avec succès."
    else:
        return f"Restaurations terminées avec {erreurs} erreurs."

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
        self.langues = {
            'fr': {
                'title': "Tri de Photos",
                'input_label': "Dossier d'entrée:",
                'output_label': "Dossier de sortie:",
                'browse': "Parcourir",
                'format_label': "Format de nom (optionnel):",
                'dry_run': "Mode Aperçu (Dry Run)",
                'export_csv': "Exporter les données EXIF en CSV",
                'min_taille_label': "Taille minimale des fichiers (Mo):",
                'min_resolution_label': "Résolution minimale des images (ex: 1920x1080):",
                'start_sorting': "Démarrer le Tri",
                'report_label': "Rapport:",
                'language_label': "Langue:",
                'undo_restore': "Restaurer les Fichiers",
                'export_success': "Les données EXIF ont été exportées vers : {0}",
                'error_no_input': "Veuillez sélectionner un dossier d'entrée.",
                'error_no_output': "Veuillez sélectionner un dossier de sortie.",
                'error_invalid_taille': "La taille minimale doit être un nombre positif.",
                'error_invalid_resolution': "La résolution minimale doit être au format WIDTHxHEIGHT (ex: 1920x1080).",
                'completed': "Le tri des photos est terminé.",
                'restored': "Tous les fichiers ont été restaurés avec succès.",
                'restored_with_errors': "Restaurations terminées avec {0} erreurs.",
            },
            'en': {
                'title': "Photo Organizer",
                'input_label': "Input Folder:",
                'output_label': "Output Folder:",
                'browse': "Browse",
                'format_label': "Filename Format (optional):",
                'dry_run': "Dry Run Mode",
                'export_csv': "Export EXIF data to CSV",
                'min_taille_label': "Minimum file size (MB):",
                'min_resolution_label': "Minimum image resolution (e.g., 1920x1080):",
                'start_sorting': "Start Sorting",
                'report_label': "Report:",
                'language_label': "Language:",
                'undo_restore': "Restore Files",
                'export_success': "EXIF data exported to: {0}",
                'error_no_input': "Please select an input folder.",
                'error_no_output': "Please select an output folder.",
                'error_invalid_taille': "Minimum size must be a positive number.",
                'error_invalid_resolution': "Minimum resolution must be in WIDTHxHEIGHT format (e.g., 1920x1080).",
                'completed': "Photo sorting is complete.",
                'restored': "All files have been successfully restored.",
                'restored_with_errors': "Restorations completed with {0} errors.",
            }
        }
        self.current_lang = 'fr'  # Default language
        self.title(self.langues[self.current_lang]['title'])
        self.geometry("800x700")
        self.resizable(False, False)
        self.create_widgets()
    
    def create_widgets(self):
        # Barre de menu pour la sélection de la langue
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        language_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.langues[self.current_lang]['language_label'], menu=language_menu)
        language_menu.add_command(label="Français", command=lambda: self.changer_langue('fr'))
        language_menu.add_command(label="English", command=lambda: self.changer_langue('en'))
        
        # Dossier d'entrée
        self.label_input = ttk.Label(self, text=self.langues[self.current_lang]['input_label'])
        self.label_input.pack(pady=10)
        
        self.frame_input = ttk.Frame(self)
        self.frame_input.pack(pady=5, padx=20, fill='x')
        
        self.entry_input = ttk.Entry(self.frame_input)
        self.entry_input.pack(side='left', fill='x', expand=True)
        
        self.button_browse_input = ttk.Button(self.frame_input, text=self.langues[self.current_lang]['browse'], command=self.browse_input)
        self.button_browse_input.pack(side='left', padx=5)
        
        # Dossier de sortie
        self.label_output = ttk.Label(self, text=self.langues[self.current_lang]['output_label'])
        self.label_output.pack(pady=10)
        
        self.frame_output = ttk.Frame(self)
        self.frame_output.pack(pady=5, padx=20, fill='x')
        
        self.entry_output = ttk.Entry(self.frame_output)
        self.entry_output.pack(side='left', fill='x', expand=True)
        
        self.button_browse_output = ttk.Button(self.frame_output, text=self.langues[self.current_lang]['browse'], command=self.browse_output)
        self.button_browse_output.pack(side='left', padx=5)
        
        # Format de nom
        self.label_format = ttk.Label(self, text=self.langues[self.current_lang]['format_label'])
        self.label_format.pack(pady=10)
        
        self.entry_format = ttk.Entry(self)
        self.entry_format.insert(0, "%Y_%m_%d_%H%M%S")
        self.entry_format.pack(pady=5, padx=20, fill='x')
        
        # Options supplémentaires
        self.var_dry_run = tk.BooleanVar()
        self.check_dry_run = ttk.Checkbutton(self, text=self.langues[self.current_lang]['dry_run'], variable=self.var_dry_run)
        self.check_dry_run.pack(pady=5)
        
        self.var_export_csv = tk.BooleanVar()
        self.check_export_csv = ttk.Checkbutton(self, text=self.langues[self.current_lang]['export_csv'], variable=self.var_export_csv)
        self.check_export_csv.pack(pady=5)
        
        # Optimisation des images
        self.var_optimiser = tk.BooleanVar()
        self.check_optimiser = ttk.Checkbutton(self, text="Optimiser les images (Compression/Redimensionnement)", variable=self.var_optimiser)
        self.check_optimiser.pack(pady=5)
        
        # Filtrage par taille
        self.label_min_taille = ttk.Label(self, text=self.langues[self.current_lang]['min_taille_label'])
        self.label_min_taille.pack(pady=10)
        
        self.entry_min_taille = ttk.Entry(self)
        self.entry_min_taille.pack(pady=5, padx=20, fill='x')
        self.entry_min_taille.insert(0, "0")
        
        # Filtrage par résolution
        self.label_min_resolution = ttk.Label(self, text=self.langues[self.current_lang]['min_resolution_label'])
        self.label_min_resolution.pack(pady=10)
        
        self.entry_min_resolution = ttk.Entry(self)
        self.entry_min_resolution.pack(pady=5, padx=20, fill='x')
        self.entry_min_resolution.insert(0, "0x0")  # "0x0" signifie aucun filtrage
        
        # Bouton de démarrage
        self.button_start = ttk.Button(self, text=self.langues[self.current_lang]['start_sorting'], command=self.start_sorting)
        self.button_start.pack(pady=10)
        
        # Barre de progression
        self.progress = ttk.Progressbar(self, orient='horizontal', length=600, mode='determinate')
        self.progress.pack(pady=10)
        
        # Zone de rapport
        self.label_report = ttk.Label(self, text=self.langues[self.current_lang]['report_label'])
        self.label_report.pack(pady=10)
        
        self.text_report = tk.Text(self, height=15, state='disabled')
        self.text_report.pack(pady=5, padx=20, fill='both', expand=True)
        
        # Bouton Undo / Restaurer
        self.button_restore = ttk.Button(self, text=self.langues[self.current_lang]['undo_restore'], command=self.restore_files)
        self.button_restore.pack(pady=10)
    
    def changer_langue(self, langue):
        if langue not in self.langues:
            return
        self.current_lang = langue
        self.title(self.langues[self.current_lang]['title'])
        # Mettre à jour tous les labels et textes
        self.label_input.config(text=self.langues[self.current_lang]['input_label'])
        self.label_output.config(text=self.langues[self.current_lang]['output_label'])
        self.button_browse_input.config(text=self.langues[self.current_lang]['browse'])
        self.button_browse_output.config(text=self.langues[self.current_lang]['browse'])
        self.label_format.config(text=self.langues[self.current_lang]['format_label'])
        self.check_dry_run.config(text=self.langues[self.current_lang]['dry_run'])
        self.check_export_csv.config(text=self.langues[self.current_lang]['export_csv'])
        self.label_min_taille.config(text=self.langues[self.current_lang]['min_taille_label'])
        self.label_min_resolution.config(text=self.langues[self.current_lang]['min_resolution_label'])
        self.button_start.config(text=self.langues[self.current_lang]['start_sorting'])
        self.label_report.config(text=self.langues[self.current_lang]['report_label'])
        self.button_restore.config(text=self.langues[self.current_lang]['undo_restore'])
        # Redémarrer l'interface pour appliquer les changements
        self.update_idletasks()
    
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
        exporter_csv = self.var_export_csv.get()
        optimiser = self.var_optimiser.get()
        
        min_taille_str = self.entry_min_taille.get()
        min_resolution = self.entry_min_resolution.get()
        
        # Validation des entrées
        if not dossier_entree:
            messagebox.showerror("Erreur", self.langues[self.current_lang]['error_no_input'])
            return
        if not dossier_sortie:
            messagebox.showerror("Erreur", self.langues[self.current_lang]['error_no_output'])
            return
        try:
            min_taille = float(min_taille_str)
            if min_taille < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", self.langues[self.current_lang]['error_invalid_taille'])
            return
        if min_resolution.lower() != "0x0":
            if not re.match(r'^\d+x\d+$', min_resolution.lower()):
                messagebox.showerror("Erreur", self.langues[self.current_lang]['error_invalid_resolution'])
                return
        else:
            min_resolution = None  # Pas de filtrage par résolution
        
        # Désactiver le bouton pour éviter les clics multiples
        self.button_start.config(state='disabled')
        self.progress['value'] = 0
        self.text_report.configure(state='normal')
        self.text_report.delete(1.0, tk.END)
        self.text_report.configure(state='disabled')
        
        # Lancer le tri dans un thread séparé pour ne pas bloquer l'interface
        threading.Thread(target=self.run_sorting, args=(
            dossier_entree, dossier_sortie, format_nom, dry_run, exporter_csv, optimiser, min_taille, min_resolution
        )).start()
    
    def run_sorting(self, dossier_entree, dossier_sortie, format_nom, dry_run, exporter_csv, optimiser, min_taille, min_resolution):
        def update_progress(current, total):
            progress_percent = (current / total) * 100
            self.progress['value'] = progress_percent
            self.update_idletasks()
        
        rapport = trier_photos(
            dossier_entree, dossier_sortie, format_nom, dry_run, 
            progress_callback=update_progress, min_taille=min_taille, 
            min_resolution=min_resolution, exporter_csv=exporter_csv, optimiser=optimiser
        )
        self.afficher_rapport(rapport)
        messagebox.showinfo("Terminé", self.langues[self.current_lang]['completed'])
        self.button_start.config(state='normal')
    
    def afficher_rapport(self, texte):
        self.text_report.configure(state='normal')
        self.text_report.delete(1.0, tk.END)
        self.text_report.insert(tk.END, texte)
        self.text_report.configure(state='disabled')
    
    def restore_files(self):
        confirmation = messagebox.askyesno("Restaurer", "Voulez-vous restaurer tous les fichiers déplacés précédemment ?")
        if confirmation:
            resultat = restaurer_fichiers()
            messagebox.showinfo("Restauration", resultat)
            self.afficher_rapport(resultat)

# --- Main ---
if __name__ == "__main__":
    configurer_logging()
    app = Application()
    app.mainloop()
