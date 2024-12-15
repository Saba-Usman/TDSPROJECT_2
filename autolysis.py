import os
import sys
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from typing import Dict, Any
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import chardet

class DataAnalyzer:
    def __init__(self, csv_path: str):
        """
        Initialize the data analyzer with a CSV file
        """
        self.csv_path = csv_path
        self.df = self._read_csv_robust()
        self.dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
        
        # AI Proxy configuration
        self.api_key = os.environ.get("AIPROXY_TOKEN", "")
        self.base_url = "https://aiproxy.sanand.workers.dev/openai/"
    
    def _read_csv_robust(self) -> pd.DataFrame:
        """
        Robustly read CSV file with multiple encoding detection strategies
        """
        # List of encodings to try
        encodings_to_try = [
            'utf-8', 
            'latin-1', 
            'iso-8859-1', 
            'cp1252',  # Windows encoding
            'utf-16',
            'ascii'
        ]

        # First, try to detect encoding using chardet
        with open(self.csv_path, 'rb') as file:
            raw_data = file.read()
            detected_encoding = chardet.detect(raw_data)['encoding']
            encodings_to_try.insert(0, detected_encoding)

        # Remove duplicates while preserving order
        encodings_to_try = list(dict.fromkeys(encodings_to_try))

        # Try reading with different encodings
        for encoding in encodings_to_try:
            try:
                # Try reading with the current encoding
                df = pd.read_csv(self.csv_path, encoding=encoding, low_memory=False)
                print(f"Successfully read CSV with {encoding} encoding")
                return df
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                print(f"Failed to read with {encoding} encoding: {e}")
                continue

        # If all encodings fail, raise an error
        raise ValueError(f"Could not read the CSV file with any of the tried encodings. "
                         f"Tried: {', '.join(encodings_to_try)}")
    
    def analyze_dataset(self) -> Dict[str, Any]:
        """
        Perform comprehensive dataset analysis
        """
        analysis = {
            "basic_stats": self._get_basic_statistics(),
            "missing_values": self._analyze_missing_values(),
            "correlations": self._compute_correlations(),
            "column_types": self._get_column_types(),
            "outliers": self._detect_outliers()
        }
        return analysis
    
    def _get_basic_statistics(self) -> Dict[str, Any]:
        """
        Compute basic statistical summary
        """
        # Convert columns to numeric, coercing errors
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Try to convert more columns to numeric
        for col in self.df.columns:
            try:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
                if not self.df[col].isna().all():
                    numeric_cols.append(col)
            except:
                pass
        
        # Remove duplicates
        numeric_cols = list(set(numeric_cols))
        
        return {
            "total_rows": len(self.df),
            "total_columns": len(self.df.columns),
            "numeric_columns": numeric_cols,
            "summary": self.df[numeric_cols].describe().to_dict() if numeric_cols else {}
        }
    
    def _analyze_missing_values(self) -> Dict[str, float]:
        """
        Analyze missing values in the dataset
        """
        missing_percentages = (self.df.isnull().sum() / len(self.df) * 100).to_dict()
        return {k: v for k, v in missing_percentages.items() if v > 0}
    
    def _compute_correlations(self) -> Dict[str, Dict[str, float]]:
        """
        Compute correlation matrix for numeric columns
        """
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 1:
            corr_matrix = self.df[numeric_cols].corr().to_dict()
            return corr_matrix
        return {}
    
    def _get_column_types(self) -> Dict[str, str]:
        """
        Get column data types
        """
        return dict(self.df.dtypes.astype(str))
    
    def _detect_outliers(self) -> Dict[str, Any]:
        """
        Detect outliers using IQR method
        """
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        outliers = {}
        for col in numeric_cols:
            try:
                Q1 = self.df[col].quantile(0.25)
                Q3 = self.df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                column_outliers = self.df[(self.df[col] < lower_bound) | (self.df[col] > upper_bound)]
                if not column_outliers.empty:
                    outliers[col] = {
                        "total_outliers": len(column_outliers),
                        "percentage": len(column_outliers) / len(self.df) * 100,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound
                    }
            except Exception as e:
                print(f"Could not detect outliers for column {col}: {e}")
        return outliers
    
    def visualize_data(self, analysis: Dict[str, Any]):
        """
        Create visualizations based on the analysis
        """
        try:
            plt.figure(figsize=(12, 8))
            
            # Correlation Heatmap
            if analysis['correlations']:
                plt.subplot(2, 2, 1)
                corr_matrix = pd.DataFrame(analysis['correlations'])
                sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, 
                            square=True, linewidths=0.5)
                plt.title('Correlation Heatmap')
                plt.tight_layout()
            
            # Missing Values Bar Chart
            if analysis['missing_values']:
                plt.subplot(2, 2, 2)
                missing_df = pd.Series(analysis['missing_values'])
                missing_df.plot(kind='bar')
                plt.title('Missing Values Percentage')
                plt.ylabel('Percentage')
                plt.xticks(rotation=45, ha='right')
            
            # Boxplot for Outliers
            numeric_cols = self.df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                plt.subplot(2, 2, 3)
                self.df[numeric_cols].boxplot()
                plt.title('Boxplot of Numeric Columns')
                plt.xticks(rotation=45, ha='right')
            
            # Distribution of First Numeric Column
            if len(numeric_cols) > 0:
                plt.subplot(2, 2, 4)
                sns.histplot(self.df[numeric_cols[0]], kde=True)
                plt.title(f'Distribution of {numeric_cols[0]}')
            
            plt.tight_layout()
            plt.savefig(f'{self.dataset_name}/analysis_plots.png')
            plt.close()
        except Exception as e:
            print(f"Error creating visualizations: {e}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_narrative(self, analysis: Dict[str, Any]):
        """
        Generate a narrative using AI Proxy and GPT-4o-Mini
        """
        narrative_prompt = f"""
        You are a data storyteller. Write a compelling narrative about the dataset named '{self.dataset_name}'.
        
        Dataset Overview:
        - Total Rows: {analysis['basic_stats']['total_rows']}
        - Total Columns: {analysis['basic_stats']['total_columns']}
        - Numeric Columns: {', '.join(map(str, analysis['basic_stats']['numeric_columns']))}

        Missing Values: {str(analysis['missing_values'])}
        Column Types: {str(analysis['column_types'])}

        Key Findings:
        1. Correlation Insights: {str(analysis['correlations'])}
        2. Outlier Analysis: {str(analysis['outliers'])}

        Please write a README.md that includes:
        - A brief description of the data
        - Key insights from the analysis
        - Potential implications or recommendations
        - A storytelling approach that makes the data engaging
        """
        
        try:
            response = requests.post(
                f"{self.base_url}v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are an expert data storyteller."},
                        {"role": "user", "content": narrative_prompt}
                    ],
                    "max_tokens": 1000
                }
            )
            
            response.raise_for_status()
            narrative = response.json()['choices'][0]['message']['content']
            
            with open(f'{self.dataset_name}/README.md', 'w', encoding='utf-8') as f:
                f.write(narrative)
        
        except requests.RequestException as e:
            print(f"Error generating narrative: {e}")
            # Fallback narrative in case of API failure
            with open(f'{self.dataset_name}/README.md', 'w', encoding='utf-8') as f:
                f.write(f"# Dataset Analysis for {self.dataset_name}\n\n"
                         f"Total Rows: {analysis['basic_stats']['total_rows']}\n"
                         f"Total Columns: {analysis['basic_stats']['total_columns']}\n\n"
                         "Automated analysis could not generate a detailed narrative.")
    
    def run_analysis(self):
        """
        Main method to run the entire analysis pipeline
        """
        # Create dataset-specific directory
        os.makedirs(self.dataset_name, exist_ok=True)
        
        # Perform analysis
        analysis = self.analyze_dataset()
        
        # Create visualizations
        self.visualize_data(analysis)
        
        # Generate narrative
        self.generate_narrative(analysis)

def main():
    if len(sys.argv) < 2:
        print("Usage: python autolysis.py <path_to_csv>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    analyzer = DataAnalyzer(csv_path)
    analyzer.run_analysis()

if __name__ == "__main__":
    main()