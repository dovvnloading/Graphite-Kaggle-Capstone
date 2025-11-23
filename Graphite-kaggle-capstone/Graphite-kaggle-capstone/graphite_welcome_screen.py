import qtawesome as qta
import random
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QFrame,
    QScrollArea, QMainWindow
)
from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QSize
from PySide6.QtGui import (
    QIcon, QGuiApplication, QPainter, QColor, QBrush, QPen,
    QLinearGradient, QRadialGradient, QFont, QTextOption, QCursor,
    QFontMetrics
)
from datetime import datetime
from graphite_core import ChatSessionManager
from graphite_dialogs import HelpDialog
from graphite_config import get_current_palette
from graphite_widgets import CustomTooltip


class GridBackgroundWidget(QWidget):
    """A widget that draws a custom background with a dot grid and a vignette effect."""
    def __init__(self, parent=None):
        """
        Initializes the GridBackgroundWidget.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.grid_size = 20
        self.grid_opacity = 0.3
        self.grid_color = QColor("#555555")

    def paintEvent(self, event):
        """
        Handles the custom painting of the background, grid, and vignette.

        Args:
            event (QPaintEvent): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fill the base background color.
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        # --- Draw Grid ---
        painter.setPen(Qt.PenStyle.NoPen)
        minor_color = QColor(self.grid_color)
        minor_color.setAlphaF(self.grid_opacity)
        painter.setBrush(minor_color)

        left, top, right, bottom = self.rect().left(), self.rect().top(), self.rect().right(), self.rect().bottom()
        
        # Align the grid to the widget's top-left corner.
        minor_left = left - (left % self.grid_size)
        minor_top = top - (top % self.grid_size)
        dot_size = 1.5

        # Iterate and draw a dot at each grid intersection.
        for x in range(minor_left, right, self.grid_size):
            for y in range(minor_top, bottom, self.grid_size):
                painter.drawEllipse(QRectF(x - dot_size / 2, y - dot_size / 2, dot_size, dot_size))

        # --- Draw Vignette Fade ---
        # A radial gradient from transparent in the center to black at the edges.
        vignette_gradient = QRadialGradient(self.rect().center(), max(self.width(), self.height()) / 1.5)
        vignette_gradient.setColorAt(0.4, QColor(30, 30, 30, 0))
        vignette_gradient.setColorAt(1.0, QColor(30, 30, 30, 255))
        painter.fillRect(self.rect(), vignette_gradient)


class StarterNodeWidget(QWidget):
    """A custom, clickable widget styled like a node, used for conversation starters."""
    clicked = Signal()

    def __init__(self, text, parent=None):
        """
        Initializes the StarterNodeWidget.

        Args:
            text (str): The text to display on the node.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setFixedSize(220, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._text = text
        self._hovered = False
        self.setMouseTracking(True)

    def enterEvent(self, event):
        """Updates hover state when the mouse enters the widget."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Updates hover state when the mouse leaves the widget."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)
        
    def paintEvent(self, event):
        """
        Handles the custom painting of the node's background, border, and text.

        Args:
            event (QPaintEvent): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        palette = get_current_palette()
        path = QRectF(0, 0, self.width(), self.height())

        # Draw background gradient.
        gradient = QLinearGradient(path.topLeft(), path.bottomLeft())
        gradient.setColorAt(0, QColor("#4a4a4a"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        painter.setBrush(gradient)

        # Draw border (white on hover, theme color otherwise).
        if self._hovered:
            pen = QPen(QColor("#ffffff"), 2)
        else:
            pen = QPen(palette.USER_NODE, 1.5)

        painter.setPen(pen)
        painter.drawRoundedRect(path, 10, 10)

        # Draw the text, centered and word-wrapped.
        painter.setPen(QColor("#e0e0e0"))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        
        text_rect = path.adjusted(10, 10, -10, -10)
        text_option = QTextOption(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        painter.drawText(text_rect, self._text, text_option)

    def mousePressEvent(self, event):
        """Emits the 'clicked' signal on a left mouse button press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ProjectButton(QWidget):
    """A custom widget representing a clickable button for a recent project."""
    clicked = Signal()

    def __init__(self, title, updated_at, parent=None):
        """
        Initializes the ProjectButton.

        Args:
            title (str): The project title.
            updated_at (str): The formatted timestamp of the last update.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self._title = title
        self._updated_at = updated_at
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        # Setup for a custom tooltip that appears after a delay.
        self.tooltip_widget = CustomTooltip(self)
        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.setInterval(500)
        self.tooltip_timer.timeout.connect(self._show_tooltip)

    def sizeHint(self):
        """Provides a recommended size for the widget."""
        return QSize(super().sizeHint().width(), 45)

    def enterEvent(self, event):
        """Starts the tooltip timer when the mouse enters the widget."""
        self._hovered = True
        self.update()
        self.tooltip_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Stops the tooltip timer and hides the tooltip when the mouse leaves."""
        self._hovered = False
        self.update()
        self.tooltip_timer.stop()
        self.tooltip_widget.hide()
        super().leaveEvent(event)
        
    def _show_tooltip(self):
        """Displays the custom tooltip near the cursor."""
        self.tooltip_widget.setText(f"Last updated: {self._updated_at}")
        self.tooltip_widget.adjustSize()
        tooltip_pos = QCursor.pos()
        self.tooltip_widget.move(tooltip_pos.x() + 15, tooltip_pos.y() + 15)
        self.tooltip_widget.show()

    def paintEvent(self, event):
        """
        Handles the custom painting of the project button.

        Args:
            event (QPaintEvent): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        palette = get_current_palette()
        rect = self.rect()
        
        # Draw background gradient.
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor("#4a4a4a"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        painter.setBrush(gradient)

        # Draw border (lighter on hover).
        if self._hovered:
            pen = QPen(palette.SELECTION.lighter(120), 2)
        else:
            pen = QPen(palette.SELECTION, 1.5)
        
        painter.setPen(pen)
        painter.drawRoundedRect(rect.adjusted(1,1,-1,-1), 6, 6)

        # Draw the project title, eliding it if it's too long.
        painter.setPen(QColor("#e0e0e0"))
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        
        title_rect = rect.adjusted(12, 0, -12, 0)
        metrics = QFontMetrics(font)
        elided_title = metrics.elidedText(self._title, Qt.TextElideMode.ElideRight, title_rect.width())
        
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)

    def mousePressEvent(self, event):
        """Emits the 'clicked' signal on a left mouse button press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class WelcomeScreen(QMainWindow):
    """
    The main window for the welcome screen, providing options to start new chats,
    load recent projects, or use conversation starters.
    """
    def __init__(self, main_window, parent=None):
        """
        Initializes the WelcomeScreen.

        Args:
            main_window (ChatWindow): The main application window to transition to.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.session_manager = ChatSessionManager(window=None)
        self.main_window = main_window

        self.setWindowTitle("Graphite - Welcome")
        self.setGeometry(0, 0, 800, 550)
        
        icon_path = r"C:\Users\Admin\source\repos\graphite_app\assets\graphite.ico"
        self.setWindowIcon(QIcon(str(icon_path)))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # The background and content are separate to allow the content to be laid out on top.
        self.grid_background = GridBackgroundWidget(central_widget)
        self.content_container = QWidget(central_widget)
        self.content_container.setStyleSheet("background: transparent;")
        
        main_layout = QVBoxLayout(self.content_container)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(25)

        # Build the UI sections.
        main_layout.addWidget(self._create_header())
        main_layout.addWidget(self._create_recent_projects())
        main_layout.addWidget(self._create_starters())
        main_layout.addStretch()

        # Center the window on the primary screen.
        screen = QGuiApplication.primaryScreen().geometry()
        self.move(int((screen.width() - self.width()) / 2) - 420, int((screen.height() - self.height()) / 2))

    def resizeEvent(self, event):
        """Ensures the background and content widgets resize with the window."""
        super().resizeEvent(event)
        self.grid_background.setGeometry(self.centralWidget().rect())
        self.content_container.setGeometry(self.centralWidget().rect())

    def _create_header(self):
        """Creates the header widget with the title and subtitle."""
        header_widget = QWidget()
        layout = QVBoxLayout(header_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Graphite")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #2ecc71; background: transparent;")
        
        subtitle = QLabel("Welcome back. Let's create something new.")
        subtitle.setStyleSheet("font-size: 14px; color: #aaaaaa; background: transparent;")
        
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return header_widget

    def _create_recent_projects(self):
        """Creates the section for displaying recent projects."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        title = QLabel("Recent Projects")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 5px; background: transparent;")
        layout.addWidget(title)
        
        recent_chats = self.session_manager.db.get_all_chats()[:5]
        
        if not recent_chats:
            no_chats_label = QLabel("No recent projects found. Start a new chat to begin!")
            no_chats_label.setStyleSheet("color: #777777; font-style: italic; background: transparent;")
            layout.addWidget(no_chats_label)
        else:
            for chat_id, chat_title, _, updated_at in recent_chats:
                updated_dt = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
                
                project_button = ProjectButton(chat_title, updated_dt.strftime('%Y-%m-%d %H:%M'))
                project_button.clicked.connect(lambda c_id=chat_id: self.load_project(c_id))
                layout.addWidget(project_button)
        
        return container

    def _create_starters(self):
        """Creates the horizontally scrolling "Conversation Starters" section."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        title = QLabel("Conversation Starters")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 5px; background: transparent;")
        layout.addWidget(title)

        self.starters_scroll_area = QScrollArea()
        self.starters_scroll_area.setWidgetResizable(True)
        self.starters_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.starters_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.starters_scroll_area.setFixedHeight(110)
        self.starters_scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        starters_widget = QWidget()
        starters_widget.setStyleSheet("background: transparent;")
        starters_layout = QHBoxLayout(starters_widget)
        starters_layout.setSpacing(15)

        starters = [
            "Explain quantum computing like I'm five years old.",
            "Draft a polite but firm email to a client about an overdue invoice.",
            "What are the key differences between Python lists and tuples?",
            "Brainstorm three unique business ideas using AI.",
            "Write a short, four-line poem about the sunset.",
            "Create a 3-day workout plan for a beginner.",
            "Summarize the plot of 'Dune' in three sentences.",
            "Generate a list of 5 healthy, easy-to-make lunch recipes.",
            "Write a Python script to rename all files in a directory.",
            "Explain the concept of blockchain in simple terms.",
            "Plan a romantic weekend getaway to a nearby city.",
            "Come up with a catchy slogan for a new coffee brand.",
            "What are some effective strategies for learning a new language?",
            "Act as a travel guide and recommend 3 things to do in Tokyo.",
            "Generate a list of interview questions for a software engineer role.",
            "Compose a brief history of the internet.",
    
            # Creative Writing & Storytelling
            "Write the opening paragraph of a mystery novel set in a small coastal town.",
            "Create a character profile for a reluctant hero in a fantasy world.",
            "Generate five creative prompts for a science fiction short story.",
            "Write a dialogue between two people meeting for the first time at a coffee shop.",
            "Come up with a plot twist for a thriller about a missing painting.",
            "Draft the first scene of a screenplay about a time traveler.",
            "Write a heartfelt letter from a parent to their child on their graduation day.",
            "Create a backstory for a villain who thinks they're the hero.",
    
            # Business & Professional
            "Write a compelling LinkedIn summary for a marketing professional.",
            "Draft a proposal for a new remote work policy.",
            "Create a SWOT analysis template for a startup.",
            "Write a professional out-of-office message for a two-week vacation.",
            "Generate talking points for a presentation on digital transformation.",
            "Draft a thank-you email after a job interview.",
            "Create a one-page business plan outline for a subscription box service.",
            "Write a cold outreach message to a potential business partner.",
            "Develop a 30-60-90 day plan for a new manager.",
            "Draft a diplomatic response to negative customer feedback.",
    
            # Education & Learning
            "Explain the theory of relativity using everyday examples.",
            "Create a study schedule for preparing for final exams.",
            "What's the best way to take effective notes during lectures?",
            "Explain photosynthesis in a way that makes it exciting.",
            "Generate 10 multiplication word problems for a 3rd grader.",
            "What are the main causes and effects of the Industrial Revolution?",
            "Create a lesson plan to teach basic fractions to elementary students.",
            "Explain machine learning algorithms without technical jargon.",
            "What are effective memorization techniques for learning vocabulary?",
            "Summarize the key themes in 'To Kill a Mockingbird.'",
    
            # Technology & Programming
            "What's the difference between GET and POST requests in web development?",
            "Write a JavaScript function to validate an email address.",
            "Explain APIs like I'm explaining it to my grandmother.",
            "What are the pros and cons of SQL vs NoSQL databases?",
            "Create a beginner's guide to Git and GitHub.",
            "Write a regex pattern to match phone numbers in various formats.",
            "What are the SOLID principles in software development?",
            "Debug this code: [explain a common programming error].",
            "What's the difference between frontend and backend development?",
            "Explain cloud computing and its benefits for small businesses.",
    
            # Health & Wellness
            "Create a weekly meal prep plan for someone trying to eat healthier.",
            "What are some effective stress management techniques for busy professionals?",
            "Design a 10-minute morning stretching routine.",
            "What are the benefits of meditation and how do I get started?",
            "Generate a grocery list for a heart-healthy diet.",
            "What are some evidence-based tips for improving sleep quality?",
            "Create a 30-day fitness challenge for building consistency.",
            "What are healthy snack alternatives to chips and candy?",
            "Explain the benefits of different types of exercise: cardio, strength, flexibility.",
            "How can I create a sustainable weight loss plan?",
    
            # Personal Development
            "What are some effective time management strategies for entrepreneurs?",
            "How do I set SMART goals for personal growth?",
            "Generate a list of thought-provoking journal prompts.",
            "What are the key habits of highly productive people?",
            "How can I improve my public speaking skills?",
            "Create a morning routine that sets up a successful day.",
            "What are practical ways to build self-confidence?",
            "How do I develop better active listening skills?",
            "What books should I read to improve my critical thinking?",
            "How can I become more resilient in the face of setbacks?",
    
            # Home & Lifestyle
            "Create a spring cleaning checklist organized by room.",
            "What are some budget-friendly ways to decorate a small apartment?",
            "Generate a list of indoor plants that are hard to kill.",
            "How do I organize a cluttered closet effectively?",
            "What are some eco-friendly alternatives to common household products?",
            "Plan a zero-waste grocery shopping trip.",
            "What are essential tools every homeowner should have?",
            "Create a monthly budget template for a young professional.",
            "How can I make my home more energy efficient?",
            "What are some creative storage solutions for small spaces?",
    
            # Travel & Adventure
            "Plan a 10-day backpacking itinerary through Europe on a budget.",
            "What should I pack for a week-long beach vacation?",
            "Recommend hidden gems to visit in Italy beyond the main tourist spots.",
            "Create a travel bucket list for adventure seekers.",
            "What are essential travel tips for first-time international travelers?",
            "Plan a perfect day trip within 100 miles of my location.",
            "What are the best apps and tools for planning a trip?",
            "How can I travel more sustainably and responsibly?",
            "Generate a packing list for a winter ski trip.",
            "What are some ways to meet locals and experience authentic culture while traveling?",
    
            # Food & Cooking
            "Write a recipe for homemade pasta from scratch.",
            "What are five essential cooking techniques every beginner should master?",
            "Create a vegetarian menu for a dinner party of six.",
            "How do I make the perfect risotto?",
            "Generate a list of pantry staples for easy weeknight cooking.",
            "What are some tips for meal planning on a tight budget?",
            "Explain the difference between baking and roasting.",
            "Create a guide to pairing wine with different types of food.",
            "What are common cooking mistakes and how do I avoid them?",
            "Write a recipe that uses leftover rotisserie chicken.",
    
            # Entertainment & Pop Culture
            "Recommend five underrated movies from the last decade.",
            "Create a playlist of 15 songs perfect for a road trip.",
            "What are the major differences between Marvel and DC comics universes?",
            "Explain the plot of 'Inception' and its ending.",
            "Generate ideas for a themed movie marathon night.",
            "What are some must-watch classic films for someone new to cinema?",
            "Recommend podcasts for someone interested in true crime.",
            "What are the most influential albums in hip-hop history?",
            "Create a beginner's guide to getting into anime.",
            "What video games are best for someone who doesn't usually play games?",
    
            # Science & Nature
            "Explain how vaccines work using simple analogies.",
            "What causes the Northern Lights?",
            "How do black holes form and what happens inside them?",
            "Explain the water cycle in an engaging way for kids.",
            "What are the main differences between weather and climate?",
            "How does DNA determine our characteristics?",
            "What would happen if the moon disappeared?",
            "Explain evolution through natural selection with clear examples.",
            "How do solar panels convert sunlight into electricity?",
            "What are the most promising renewable energy technologies?",
    
            # Relationships & Social
            "How do I start a conversation with someone I just met?",
            "What are healthy boundaries in friendships and how do I set them?",
            "Generate thoughtful questions to ask on a first date.",
            "How can I be more empathetic in my relationships?",
            "What are effective conflict resolution strategies for couples?",
            "How do I maintain long-distance friendships?",
            "What are some creative date night ideas for couples on a budget?",
            "How can I politely decline an invitation without hurting feelings?",
            "What are signs of a toxic relationship and how do I address them?",
            "How do I make new friends as an adult?",
    
            # Productivity & Organization
            "Create a digital filing system for personal documents.",
            "What's the Pomodoro Technique and how do I use it effectively?",
            "Generate a template for a daily to-do list that actually works.",
            "How can I stop procrastinating on important tasks?",
            "What are the best apps for staying organized in 2025?",
            "Create a system for managing email overload.",
            "How do I prioritize tasks when everything feels urgent?",
            "What are effective ways to minimize distractions while working?",
            "Design a weekly planning routine for maximum productivity.",
            "How can I batch similar tasks to save time?",
    
            # Finance & Money
            "Explain the basics of investing in index funds for beginners.",
            "How do I create an emergency fund from scratch?",
            "What's the 50/30/20 budgeting rule and how do I apply it?",
            "Generate a list of ways to earn passive income.",
            "How do credit scores work and how can I improve mine?",
            "What should I know about retirement accounts (401k, IRA, etc.)?",
            "Create a debt payoff strategy using the snowball method.",
            "What are common financial mistakes people make in their 20s?",
            "How do I negotiate a higher salary during a job offer?",
            "Explain compound interest using a simple example.",
    
            # Fun & Games
            "Create 10 riddles with answers for a family game night.",
            "Generate ideas for a themed costume party.",
            "What are some fun team-building activities for remote teams?",
            "Create a scavenger hunt with clues for kids.",
            "What are engaging icebreaker questions for a small group?",
            "Design a trivia quiz about 90s pop culture.",
            "Generate creative writing prompts for a writing workshop.",
            "What are some two-player card games using a standard deck?",
            "Create a list of conversation starters for a dinner party.",
            "What are fun outdoor activities for a family reunion?",
    
            # Miscellaneous & Unique
            "If you could have dinner with any three historical figures, who would you choose and why?",
            "Write a product description for an imaginary invention.",
            "What would a day in the life of a medieval blacksmith look like?",
            "Create a fake conspiracy theory that sounds surprisingly believable.",
            "Generate five 'shower thoughts' that make you think.",
            "What are some mind-blowing facts about space?",
            "Write a how-to guide for something completely ordinary in an overly dramatic way.",
            "What would aliens think if they intercepted our internet traffic?",
            "Create a humorous instruction manual for being human.",
            "If animals could talk, which species would be the rudest?",
        ]
        
        random.shuffle(starters)
        
        # Duplicate the list to create a seamless looping animation.
        full_starters_list = starters + starters

        for prompt in full_starters_list:
            starter_node = StarterNodeWidget(prompt)
            starter_node.clicked.connect(lambda p=prompt: self.start_new_chat(prompt=p))
            starters_layout.addWidget(starter_node)

        self.starters_scroll_area.setWidget(starters_widget)
        layout.addWidget(self.starters_scroll_area)
        
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(30)  # ~33 FPS for smooth animation
        self.scroll_timer.timeout.connect(self._tick_scroll)
        
        # Use a short delay to ensure the layout has been calculated before starting the animation.
        QTimer.singleShot(100, self._setup_starter_animation)
        
        return container
    
    def _setup_starter_animation(self):
        """Sets up the automatic scrolling and pauses on hover."""
        self.scroll_timer.start()
        # Pause animation when the user hovers over the scroll area.
        self.starters_scroll_area.enterEvent = lambda event: self.scroll_timer.stop()
        self.starters_scroll_area.leaveEvent = lambda event: self.scroll_timer.start()
        
    def _tick_scroll(self):
        """
        Called by a timer to increment the horizontal scroll position, creating
        a seamless looping effect.
        """
        scrollbar = self.starters_scroll_area.horizontalScrollBar()
        max_val = scrollbar.maximum()
        
        if max_val == 0: return # Not scrollable yet.

        current_val = scrollbar.value()
        new_val = current_val + 1 # Scroll speed
        
        # The content is duplicated, so the halfway point is the reset trigger.
        half_point = max_val / 2
        
        if new_val >= half_point:
            # We've scrolled past the first set. Jump back to the equivalent
            # position at the start to create the illusion of a seamless loop.
            scrollbar.setValue(int(new_val - half_point))
        else:
            scrollbar.setValue(new_val)

    def load_project(self, chat_id):
        """
        Loads a selected project into the main window and closes the welcome screen.

        Args:
            chat_id (int): The ID of the chat session to load.
        """
        if not self.main_window:
            return
        self.main_window.session_manager.load_chat(chat_id)
        self.main_window.update_title_bar()
        self.main_window.activateWindow()
        self.main_window.raise_()
        self.close()

    def start_new_chat(self, prompt=None):
        """
        Starts a new chat in the main window, optionally with an initial prompt,
        and closes the welcome screen.

        Args:
            prompt (str, optional): An initial prompt to send. Defaults to None.
        """
        if not self.main_window:
            return
        self.main_window.new_chat()
        self.main_window.activateWindow()
        self.main_window.raise_()
        if prompt and isinstance(prompt, str):
            self.main_window.start_with_prompt(prompt)
        self.close()

    def open_library(self):
        """Opens the chat library in the main window."""
        if not self.main_window:
            return
        self.main_window.show_library()
        self.main_window.activateWindow()
        self.main_window.raise_()